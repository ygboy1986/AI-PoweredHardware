"""第 4 周示例：让大模型为规则结果生成受 JSON Schema 约束的解释。"""

import json
import os
from typing import Protocol

import httpx

from .models import AIHealthExplanation, RiskReport


class ExplanationError(RuntimeError):
    """模型调用或返回内容不符合安全要求。"""


class HealthExplainer(Protocol):
    """无论使用模拟器还是云端模型，对 Agent 都提供同一个 explain 方法。"""

    provider_name: str

    def explain(self, report: RiskReport) -> AIHealthExplanation: ...


class MockHealthExplainer:
    """离线学习模式：不调用任何大模型 API，但返回与真实接口相同的结构。"""

    provider_name = "mock"

    def explain(self, report: RiskReport) -> AIHealthExplanation:
        reasons = report.reasons[:3]
        return AIHealthExplanation(
            risk_level=report.risk_level,
            summary=f"检测到{report.risk_level.value}风险：" + "；".join(reasons),
            reasons=reasons,
            requires_human_confirmation=report.requires_human_confirmation,
        )


class OpenAIHealthExplainer:
    """OpenAI Responses API 适配器，使用 strict JSON Schema 获取固定输出。"""

    provider_name = "openai"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=httpx.Timeout(20))

    def explain(self, report: RiskReport) -> AIHealthExplanation:
        schema = AIHealthExplanation.model_json_schema()
        instructions = (
            "你是老人手表健康数据解释助手。只能解释提供的规则报告，不做医疗诊断，"
            "不编造证据，不建议自动通知或自动报警。risk_level 和 "
            "requires_human_confirmation 必须与规则报告完全一致。"
        )
        body = {
            "model": self.model,
            "instructions": instructions,
            "input": json.dumps(report.model_dump(mode="json"), ensure_ascii=False),
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "health_explanation",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        try:
            response = self.client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            explanation = AIHealthExplanation.model_validate_json(response.json()["output_text"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ExplanationError("大模型未返回有效的结构化解释") from error

        # 规则优先：即使模型返回了合规 JSON，也不能允许它降低风险或跳过人工确认。
        if (explanation.risk_level != report.risk_level or
                explanation.requires_human_confirmation != report.requires_human_confirmation):
            raise ExplanationError("模型解释试图改变规则引擎的安全结论")
        return explanation


def get_health_explainer() -> HealthExplainer:
    """默认使用 mock；仅当显式配置 openai 模式时才读取和使用 API Key。"""
    mode = os.getenv("GUARDIAN_LLM_MODE", "mock").lower()
    if mode == "mock":
        return MockHealthExplainer()
    if mode != "openai":
        raise ExplanationError("GUARDIAN_LLM_MODE 仅支持 mock 或 openai")

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not api_key or not model:
        raise ExplanationError("openai 模式需要 OPENAI_API_KEY 和 OPENAI_MODEL")
    return OpenAIHealthExplainer(api_key, model)
