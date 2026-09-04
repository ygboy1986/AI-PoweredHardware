from time import perf_counter
from uuid import uuid4

from .health_rules import HealthRuleEngine
from .models import Evidence, HealthSnapshot, RiskLevel, RiskReport, ToolAudit
from .tools import ToolDefinition


class GuardianRiskAgent:
    """Agent 只编排只读工具；风险升级由确定性规则决定。"""

    def __init__(self, tools: dict[str, ToolDefinition], health_engine: HealthRuleEngine | None = None) -> None:
        # tools 保存可自动执行的只读工具；health_engine 负责健康指标的规则判断。
        self.tools = tools
        self.health_engine = health_engine
    #分析今日状态的方法
    def analyze_today(self, device_id: int) -> RiskReport:
        """查询预置设备工具，生成“今天是否异常”的综合风险报告。"""

        evidence: list[Evidence] = []
        audit: list[ToolAudit] = []
        # Agent 可自动调用只读工具，并为每次调用保留耗时与成功状态。
        for name, tool in self.tools.items():
            started = perf_counter()
            try:
                result = tool.handler(device_id)
                # 将工具返回的字典转换为统一证据模型。
                evidence.append(Evidence(**result))
                audit.append(ToolAudit(tool=name, risk=tool.risk, success=True,
                                       duration_ms=round((perf_counter() - started) * 1000)))
            except Exception:
                # 单个工具失败不会让整个风险分析崩溃，而是记录失败供后续降级处理。
                audit.append(ToolAudit(tool=name, risk=tool.risk, success=False,
                                       duration_ms=round((perf_counter() - started) * 1000)))

        details = " ".join(item.detail for item in evidence)
        # 安全边界：任何模型总结只能解释本规则结果，不能降低已有的高风险等级。
        if "疑似跌倒" in details:
            level, confidence = RiskLevel.CRITICAL, 0.92
            reasons = ["设备上报疑似跌倒，须立即进入既有紧急流程", "设备电量偏低，后续追踪可能受影响"]
        elif "电量 15%" in details:
            level, confidence = RiskLevel.MEDIUM, 0.80
            reasons = ["设备电量低于 20%"]
        else:
            level, confidence = RiskLevel.LOW, 0.75
            reasons = ["未发现跌倒、越界或离线信号"]

        needs_confirmation = level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        # 所有风险结果先在 iPhone 呈现；高风险仅增加“需要确认”的建议，不直接写操作。
        actions = ["在 iPhone 本地展示风险与证据", "发起语音确认"]
        if needs_confirmation:
            actions.append("经监护人确认后发送通知")
        return RiskReport(
            request_id=str(uuid4()), device_id=device_id, risk_level=level,
            confidence=confidence, reasons=reasons, evidence=evidence,
            recommended_actions=actions, requires_human_confirmation=needs_confirmation,
            fallback_used=any(not item.success for item in audit), tool_audit=audit,
        )
    #分析健康数据的方法
    def analyze_health(self, device_id: int, snapshot: HealthSnapshot) -> RiskReport:

        """分析 iOS/手表上传的健康快照，并把多条规则发现汇总为最终风险。"""

        #检查规则引擎
        if self.health_engine is None:
            # 没有规则引擎时禁止分析，避免在无安全规则的情况下给出健康结论。
            raise RuntimeError("health rule engine is not configured")
        findings = self.health_engine.evaluate(snapshot)
        print(f"析 iOS/手表上传的健康快照:{snapshot}")
        # 风险等级映射为可比较的数字，便于从多条发现中选出最高等级。
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        # highest = max(
        #     (item.risk_level for item in findings),
        #     key=order.get,
        #     default=RiskLevel.LOW
        # )
        highest = RiskLevel.LOW
        for item in findings:
            current_lenvel = item.risk_level
            if order[current_lenvel] > order[highest]:
                highest = current_lenvel
                
        # 当前置信度仅表示规则是否命中；未来接入模型时也不能覆盖更高的规则风险等级。
        return RiskReport(
            request_id=str(uuid4()), device_id=device_id, risk_level=highest,
            confidence=0.95 if findings else 0.80,
            reasons=[item.reason for item in findings] or ["当前数据未触发已注册的健康预警规则"],
            evidence=[item.evidence for item in findings],
            # 高风险建议需要监护人确认，普通风险则继续定期监测。
            recommended_actions=(['在 iPhone 本地显示风险与证据', '发起语音确认', '经监护人确认后发送通知']
                                 if highest in {RiskLevel.HIGH, RiskLevel.CRITICAL}
                                 else ['继续监测，并按计划同步数据']),
            requires_human_confirmation=highest in {RiskLevel.HIGH, RiskLevel.CRITICAL},
            fallback_used=False, tool_audit=[],
        )
