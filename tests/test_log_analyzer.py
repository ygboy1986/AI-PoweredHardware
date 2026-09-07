from guardian_ai.log_analyzer import LogAIAnalyzer
from guardian_ai.models import LogAnalysisRequest


def test_pydantic_validation_log_returns_structured_analysis(monkeypatch) -> None:
    monkeypatch.setenv("GUARDIAN_LLM_MODE", "mock")
    result = LogAIAnalyzer().analyze(LogAnalysisRequest(
        source="Error.log",
        log_text="[2026-09-01 10:47:22] ERROR:字段:battery 原因:Input should be less than or equal to 100",
    ))
    assert result.analysis.error_type == "validation_error"
    assert result.parsed_entries[0].level == "error"


def test_json_error_log_returns_json_parse_error(monkeypatch) -> None:
    monkeypatch.setenv("GUARDIAN_LLM_MODE", "mock")
    result = LogAIAnalyzer().analyze(LogAnalysisRequest(
        log_text="ERROR: JSON input should be string, bytes or bytearray",
    ))
    assert result.analysis.error_type == "json_parse_error"


def test_timeout_log_returns_safe_warning(monkeypatch) -> None:
    monkeypatch.setenv("GUARDIAN_LLM_MODE", "mock")
    result = LogAIAnalyzer().analyze(LogAnalysisRequest(
        log_text="2026-09-07 10:00:00 [ERROR] request timed out",
    ))
    assert result.analysis.error_type == "network_timeout"
    assert result.analysis.danger_warnings
