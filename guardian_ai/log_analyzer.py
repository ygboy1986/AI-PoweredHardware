"""第 4 周实战：日志解析 + 大模型结构化输出 + 失败降级。"""

import json
import os
import re
from datetime import datetime
from typing import Protocol

import httpx

from .models import LogAIAnalysis, LogAnalysisResponse, LogAnalysisRequest, ParsedLogEntry


class LogAnalysisError(RuntimeError):
    """真实模型调用失败或输出不符合日志分析 JSON 契约。"""


class LogExplainer(Protocol):
    provider_name: str

    def explain(self, request: LogAnalysisRequest,
                entries: list[ParsedLogEntry]) -> LogAIAnalysis: ...


class LogParser:
    """先用确定性代码解析常见格式，模型只分析必要的、脱敏后的文本。"""

    bracket_pattern = re.compile(r"^\[(?P<time>[^\]]+)\]\s*(?P<level>[A-Z]+)\s*:\s*(?P<message>.+)$")
    bracket_level_pattern = re.compile(r"^(?P<time>\S+(?:\s+\S+)?)\s+\[(?P<level>[A-Z]+)\]\s*(?P<message>.+)$")

    def parse(self, log_text: str) -> list[ParsedLogEntry]:
        entries: list[ParsedLogEntry] = []
        for raw_line in log_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = self.bracket_pattern.match(line) or self.bracket_level_pattern.match(line)
            if match:
                entries.append(ParsedLogEntry(
                    timestamp=self._parse_time(match.group("time")),
                    level=match.group("level").lower(),
                    message=match.group("message"),
                ))
            else:
                # 第三类：无统一前缀的 Python Traceback、iOS Crash 或普通文本。
                level = "error" if any(word in line.lower() for word in ("error", "exception", "fatal")) else "info"
                entries.append(ParsedLogEntry(level=level, message=line))
        return entries or [ParsedLogEntry(level="info", message="未发现可分析的非空日志行")]

    @staticmethod
    def _parse_time(raw_time: str) -> datetime | None:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(raw_time, pattern)
            except ValueError:
                pass
        return None


class MockLogExplainer:
    """离线模式：用简单关键词实现可学习、可测试的结构化结果。"""

    provider_name = "mock"

    def explain(self, request: LogAnalysisRequest,
                entries: list[ParsedLogEntry]) -> LogAIAnalysis:
        text = "\n".join(entry.message for entry in entries).lower()
        evidence = [entry.message for entry in entries if entry.level == "error"][:3]
        evidence = evidence or [entries[0].message]
        if "json input" in text or "jsondecode" in text:
            return LogAIAnalysis(
                error_type="json_parse_error", severity="medium",
                summary="日志显示 JSON 输入格式不正确。", key_evidence=evidence,
                possible_causes=["传入对象而非 JSON 字符串", "请求体字段缺失或类型错误"],
                check_steps=["打印发送前的 JSON 文本", "确认 Content-Type 为 application/json"],
                danger_warnings=[],
            )
        if "validation error" in text or "input should" in text:
            return LogAIAnalysis(
                error_type="validation_error", severity="low",
                summary="日志显示输入数据未通过字段校验。", key_evidence=evidence,
                possible_causes=["字段值超出允许范围", "必填字段格式或长度不符合要求"],
                check_steps=["检查错误信息中的字段名", "在发送前按 Pydantic 模型校验数据"],
                danger_warnings=[],
            )
        if "timeout" in text or "timed out" in text:
            return LogAIAnalysis(
                error_type="network_timeout", severity="medium",
                summary="日志显示网络请求超时。", key_evidence=evidence,
                possible_causes=["设备平台响应缓慢", "网络不可用或超时设置过短"],
                check_steps=["检查网络连接", "记录请求耗时并按策略重试"],
                danger_warnings=["不要无限重试，以免重复触发设备操作。"],
            )
        return LogAIAnalysis(
            error_type="unknown", severity="low", summary="未识别到已知错误模式。",
            key_evidence=evidence, possible_causes=["日志信息不足或属于新错误类型"],
            check_steps=["补充完整错误堆栈", "为该错误新增测试样本和规则"], danger_warnings=[],
        )


class OpenAILogExplainer:
    """真实 OpenAI 模式：要求 Responses API 返回严格匹配 Pydantic Schema 的 JSON。"""

    provider_name = "openai"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self.api_key, self.model = api_key, model
        self.client = client or httpx.Client(timeout=httpx.Timeout(20))

    def explain(self, request: LogAnalysisRequest,
                entries: list[ParsedLogEntry]) -> LogAIAnalysis:
        instructions = (
            "你是软件日志分析助手。只根据给出的日志说明错误类型、证据、可能原因和检查步骤。"
            "不要编造日志中不存在的信息；不要建议删除数据、重置设备或泄露密钥；不要进行医疗诊断。"
        )
        body = {
            "model": self.model, "instructions": instructions, "store": False,
            "input": json.dumps({"source": request.source, "entries": [item.model_dump(mode="json") for item in entries]}, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "log_ai_analysis",
                                   "strict": True, "schema": LogAIAnalysis.model_json_schema()}},
        }
        try:
            response = self.client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            return LogAIAnalysis.model_validate_json(response.json()["output_text"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise LogAnalysisError("大模型未返回有效的日志分析 JSON") from error


class LogAIAnalyzer:
    """编排器：确定性解析 → 模型解释；模型失败时降级为 Mock 分析。"""

    def __init__(self, parser: LogParser | None = None) -> None:
        self.parser = parser or LogParser()

    def analyze(self, request: LogAnalysisRequest) -> LogAnalysisResponse:
        entries = self.parser.parse(request.log_text)
        try:
            explainer = self._get_explainer()
            analysis = explainer.explain(request, entries)
            provider, fallback_used = explainer.provider_name, False
        except LogAnalysisError:
            analysis = MockLogExplainer().explain(request, entries)
            provider, fallback_used = "mock_fallback", True
        return LogAnalysisResponse(
            source=request.source, parsed_entries=entries, analysis=analysis,
            ai_provider=provider, fallback_used=fallback_used,
        )

    @staticmethod
    def _get_explainer() -> LogExplainer:
        mode = os.getenv("GUARDIAN_LLM_MODE", "mock").lower()
        if mode == "mock":
            return MockLogExplainer()
        if mode != "openai":
            raise LogAnalysisError("GUARDIAN_LLM_MODE 仅支持 mock 或 openai")
        api_key, model = os.getenv("OPENAI_API_KEY"), os.getenv("OPENAI_MODEL")
        if not api_key or not model:
            raise LogAnalysisError("openai 模式需要 OPENAI_API_KEY 和 OPENAI_MODEL")
        return OpenAILogExplainer(api_key, model)
