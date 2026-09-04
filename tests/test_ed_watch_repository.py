import json

import httpx

from guardian_ai.ed_watch_repository import EdWatchHealthRepository


def test_health_info_is_mapped_to_guardian_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/Device/HealthInfo"
        payload = json.loads(request.content)
        assert payload["DeviceId"] == 71372
        assert payload["Token"] == "test-token"
        assert request.headers["token"] == "test-token"
        return httpx.Response(200, json={
            "State": 0, "DeviceId": 71372, "HeartRate": 132,
            "BloodOxygen": 88, "BloodMax": 150, "BloodMin": 95,
            "BloodSuger": 0, "Temperature": 36.5,
            "LastUpdateTime": "2026-09-04 10:00:00",
        })

    repository = EdWatchHealthRepository(
        "http://example.test/api/", "test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    snapshot = repository.fetch_health_snapshot(71372)

    assert {item.metric for item in snapshot.readings} == {
        "heart_rate", "spo2", "blood_pressure_systolic",
        "blood_pressure_diastolic", "body_temperature",
    }
