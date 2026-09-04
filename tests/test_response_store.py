import json

from guardian_ai.models import RiskLevel, RiskReport
from guardian_ai.response_store import ResponseStore


def test_response_is_appended_as_one_jsonl_line(tmp_path) -> None:
    store = ResponseStore(tmp_path)
    report = RiskReport(
        request_id="request-1", device_id=1001, risk_level=RiskLevel.LOW,
        confidence=0.8, reasons=["正常"], evidence=[], recommended_actions=[],
        requires_human_confirmation=False, fallback_used=False, tool_audit=[],
    )

    file_path = store.append("/v1/devices/{device_id}/health-analysis", report)

    lines = file_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["response"]["request_id"] == "request-1"
    assert saved["endpoint"] == "/v1/devices/{device_id}/health-analysis"
