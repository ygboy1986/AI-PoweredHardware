import pytest

from guardian_ai.ed_watch_repository import EdWatchAPIError, EdWatchHealthRepository


def test_non_ascii_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ED_WATCH_API_TOKEN", "请替换真实Token")
    with pytest.raises(EdWatchAPIError, match="格式错误"):
        EdWatchHealthRepository.from_environment()
