"""将业务接口的结构化返回结果追加保存为 JSON Lines 文件。"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ResponseStore:
    """本地演示用响应存储。

    一行对应一次接口返回，因此可逐行读取、导入 Pandas 或后续迁移到数据库。
    不记录 HTTP 请求头、Token 或原始 `.env` 配置。
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        configured_directory = directory or os.getenv(
            "GUARDIAN_RESPONSE_DATA_DIR", "data/guardian_responses"
        )
        self.directory = Path(configured_directory)

    def append(self, endpoint: str, response: BaseModel | dict[str, Any]) -> Path:
        """将接口路径、写入时间和返回数据追加到当天的 JSONL 文件。"""
        now = datetime.now(timezone.utc)
        self.directory.mkdir(parents=True, exist_ok=True)
        file_path = self.directory / f"responses-{now.date().isoformat()}.jsonl"
        payload = response.model_dump(mode="json") if isinstance(response, BaseModel) else response
        record = {
            "recorded_at": now.isoformat(),
            "endpoint": endpoint,
            "response": payload,
        }
        with file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return file_path
