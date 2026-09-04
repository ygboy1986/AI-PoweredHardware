"""ED Watch 平台的服务端适配器。

本文件只在 Guardian 后端运行。Token 始终从环境变量读取，不能下发给 iOS。
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

from .models import HealthReading, HealthSnapshot


class EdWatchAPIError(RuntimeError):
    """ED Watch 配置、网络或业务返回异常。"""


class EdWatchHealthRepository:
    """调用 `Device/HealthInfo`，并转换成 Guardian 的统一健康数据结构。"""

    def __init__(self, base_url: str, token: str, app_id: int = 125,
                 time_offset: int = 8, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.app_id = app_id
        self.time_offset = time_offset
        # 可注入 client，单元测试时用 MockTransport，避免访问真实设备平台。
        self.client = client or httpx.Client(timeout=httpx.Timeout(10))

    @classmethod
    def from_environment(cls) -> "EdWatchHealthRepository":
        """从 .env / 系统环境变量创建仓库，缺少配置时只在实际调用时失败。"""
        # FastAPI 启动时加载本项目 .env；其中的 Token 仍只存在于服务端进程内。
        load_dotenv()
        base_url = os.getenv("ED_WATCH_API_BASE_URL", "http://cqapi.ed-watch.com/api/")
        token = os.getenv("ED_WATCH_API_TOKEN")
        if not token:
            raise EdWatchAPIError("缺少 ED_WATCH_API_TOKEN；请只在服务端 .env 中配置")
        # 当前设备平台的 Token 会同时放入 HTTP 请求头，必须是可安全传输的 ASCII 字符。
        # 中文占位文字、全角引号或复制进来的说明文字都不是有效 Token。
        if not token.isascii():
            raise EdWatchAPIError("ED_WATCH_API_TOKEN 格式错误；请替换为真实的 ASCII 登录 Token")
        return cls(
            base_url=base_url,
            token=token,
            app_id=int(os.getenv("ED_WATCH_APP_ID", "125")),
            time_offset=int(os.getenv("ED_WATCH_TIME_OFFSET", "8")),
        )

    def fetch_health_snapshot(self, device_id: int) -> HealthSnapshot:
        """请求真实健康信息，并转换成心率、血氧、血压、血糖和体温读数。"""
        payload = {
            "AppId": self.app_id,
            "DeviceId": device_id,
            "Language": "en",
            "TimeOffset": self.time_offset,
            "Token": self.token,
        }
        try:
            # 与现有设备列表接口保持一致：Token 同时位于业务参数和请求头中。
            response = self.client.post(
                f"{self.base_url}/Device/HealthInfo",
                json=payload,
                headers={"Accept": "application/json", "token": self.token},
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise EdWatchAPIError("调用 ED Watch HealthInfo 失败") from error

        # 部分网关会把业务数据放进 Data；题目提供的接口示例则直接返回字段。
        health = data.get("Data", data) if isinstance(data, dict) else None
        if not isinstance(health, dict):
            raise EdWatchAPIError("HealthInfo 返回格式不是 JSON 对象")
        if health.get("State", 0) != 0:
            raise EdWatchAPIError(f"HealthInfo 业务失败：State={health.get('State')}")

        observed_at = self._parse_time(
            health.get("LastUpdateTime") or health.get("HealthHeartTime")
        )
        # 0 表示设备尚无该项有效测量，不应错误地当成真实生理数值。
        mappings = [
            ("HeartRate", "heart_rate", "bpm"),
            ("BloodOxygen", "spo2", "%"),
            ("BloodMax", "blood_pressure_systolic", "mmHg"),
            ("BloodMin", "blood_pressure_diastolic", "mmHg"),
            # BloodSuger 的单位需在设备协议中确认，因此先标记为 unknown。
            ("BloodSuger", "blood_sugar", "unknown"),
            ("Temperature", "body_temperature", "℃"),
        ]
        readings = [
            HealthReading(metric=metric, value=float(health[field]), unit=unit,
                          measured_at=observed_at, source="ed_watch_api")
            for field, metric, unit in mappings
            if isinstance(health.get(field), (int, float)) and health[field] > 0
        ]
        if not readings:
            raise EdWatchAPIError("设备未返回有效健康读数；请确认设备已同步并有测量数据")
        return HealthSnapshot(readings=readings, trajectory=[], has_suspected_fall=False)

    def _parse_time(self, raw_time: Any) -> datetime:
        """兼容接口常见的空字符串、ISO 时间和 `YYYY-MM-DD HH:MM:SS` 格式。"""
        tz = timezone(timedelta(hours=self.time_offset))
        if not raw_time:
            return datetime.now(tz)
        try:
            return datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(str(raw_time), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            except ValueError:
                return datetime.now(tz)
