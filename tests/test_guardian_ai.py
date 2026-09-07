from fastapi.testclient import TestClient

from guardian_ai.main import app

client = TestClient(app)


def test_critical_event_requires_human_confirmation() -> None:
    response = client.post("/v1/devices/1001/risk-report")
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "critical"
    assert body["requires_human_confirmation"] is True
    assert all(item["risk"] == "read_only" for item in body["tool_audit"])


def test_confirm_action_is_idempotent() -> None:
    payload = {"request_id": "test-request", "device_id": 1001,
               "action": "send_guardian_notification", "confirmed_by": "guardian"}
    assert client.post("/v1/actions/confirm", json=payload).status_code == 201
    assert client.post("/v1/actions/confirm", json=payload).status_code == 409


def test_health_analysis_is_extensible_and_requires_confirmation_for_spo2() -> None:
    payload = {"readings": [{"metric": "spo2", "value": 88, "unit": "%",
                              "measured_at": "2026-09-02T10:00:00Z", "source": "watch"}],
               "trajectory": [], "has_suspected_fall": False}
    response = client.post("/v1/devices/1001/health-analysis", json=payload)
    assert response.status_code == 200
    assert response.json()["risk_level"] == "high"
    assert response.json()["requires_human_confirmation"] is True


def test_ai_health_explanation_works_without_api_key_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("GUARDIAN_LLM_MODE", "mock")
    payload = {"readings": [{"metric": "heart_rate", "value": 132, "unit": "bpm",
                              "measured_at": "2026-09-07T10:00:00Z", "source": "watch"}],
               "trajectory": [], "has_suspected_fall": False}
    response = client.post("/v1/devices/1001/ai-health-explanation", json=payload)
    assert response.status_code == 200
    assert response.json()["ai_provider"] == "mock"
    assert response.json()["ai_explanation"]["risk_level"] == "high"
