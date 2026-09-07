from guardian_ai.llm_explainer import MockHealthExplainer
from guardian_ai.models import RiskLevel, RiskReport


def test_mock_explainer_keeps_rule_safety_decision() -> None:
    report = RiskReport(
        request_id="request-1", device_id=1001, risk_level=RiskLevel.HIGH,
        confidence=0.95, reasons=["心率过高"], evidence=[],
        recommended_actions=["确认通知"], requires_human_confirmation=True,
        fallback_used=False, tool_audit=[],
    )
    result = MockHealthExplainer().explain(report)
    assert result.risk_level == RiskLevel.HIGH
    assert result.requires_human_confirmation is True
