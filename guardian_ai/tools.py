from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .models import ToolRisk


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    risk: ToolRisk
    handler: Callable[[int], dict[str, Any]]


class DemoDeviceRepository:
    """用于本地演示；生产环境替换为受权限控制的业务服务。"""

    def __init__(self) -> None:
        self._now = datetime.now(timezone.utc)

    def location(self, device_id: int) -> dict[str, Any]:
        return {"source": "location", "observed_at": self._now, "detail": "位于家庭围栏内，定位精度 18m"}

    def battery(self, device_id: int) -> dict[str, Any]:
        return {"source": "device", "observed_at": self._now, "detail": "电量 15%，设备在线"}

    def fence_events(self, device_id: int) -> dict[str, Any]:
        return {"source": "fence", "observed_at": self._now, "detail": "过去 24 小时无越界事件"}

    def health_summary(self, device_id: int) -> dict[str, Any]:
        return {"source": "health", "observed_at": self._now, "detail": "检测到疑似跌倒事件；最近心率 118 bpm"}

    def bluetooth_state(self, device_id: int) -> dict[str, Any]:
        return {"source": "bluetooth", "observed_at": self._now, "detail": "蓝牙连接正常"}



def build_read_only_tools(repository: DemoDeviceRepository) -> dict[str, ToolDefinition]:
    return {
       
        "getDeviceLocation": ToolDefinition("getDeviceLocation", ToolRisk.READ_ONLY, repository.location), #查询位置
        "getDeviceBattery": ToolDefinition("getDeviceBattery", ToolRisk.READ_ONLY, repository.battery), #查询电量
        "getFenceEvents": ToolDefinition("getFenceEvents", ToolRisk.READ_ONLY, repository.fence_events), #查询围栏事件
        "getHealthSummary": ToolDefinition("getHealthSummary", ToolRisk.READ_ONLY, repository.health_summary), #查询健康摘要
        "getBluetoothState": ToolDefinition("getBluetoothState", ToolRisk.READ_ONLY, repository.bluetooth_state), #查询蓝牙状态
    }
