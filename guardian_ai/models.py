from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# 风险等级按严重程度从低到高排列，供规则引擎和 iOS 界面统一使用。
class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# 工具分级：只读工具可由 Agent 自动调用；高风险写工具必须人工确认。
class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    HIGH_RISK_WRITE = "high_risk_write"


class Evidence(BaseModel):
    """风险结论对应的原始证据，便于用户查看原因与管理员追溯。"""

    # 证据来源，例如 wearable、watch、location 或 health。
    source: str
    # 采用设备记录时间，而不是服务端接收时间。
    observed_at: datetime
    # 保留人类可读的原始信息，例如 "spo2=88%"。
    detail: str


class ToolAudit(BaseModel):
    """记录每个工具的调用结果，用于排查超时、失败和降级。"""

    tool: str
    risk: ToolRisk
    success: bool
    duration_ms: int = Field(ge=0)


class RiskReport(BaseModel):
    """后端返回给 iOS 的统一风险报告。"""

    # 每次分析生成唯一 ID，后续人工确认与审计都使用它关联。
    request_id: str
    device_id: int
    #危险等级
    risk_level: RiskLevel
    # 置信度仅作参考，不能代替确定性报警规则。
    confidence: float = Field(ge=0, le=1)
    reasons: list[str]
    #风险结论来源
    evidence: list[Evidence]
    recommended_actions: list[str]
    # true 表示建议涉及通知、报警等操作，必须先让监护人确认。
    requires_human_confirmation: bool
    fallback_used: bool
    tool_audit: list[ToolAudit]


class AIHealthExplanation(BaseModel):
    """大模型对规则结果的用户可读解释，不承担医疗诊断或报警决策。"""

    risk_level: RiskLevel
    summary: str = Field(min_length=1, max_length=200)
    reasons: list[str] = Field(min_length=1, max_length=5)
    requires_human_confirmation: bool


class ExplainedRiskReport(BaseModel):
    """规则报告与模型解释的组合响应。"""

    risk_report: RiskReport
    ai_explanation: AIHealthExplanation
    ai_provider: str
    fallback_used: bool


class HealthReading(BaseModel):
    """一条可扩展的健康读数。metric 可使用 heart_rate、spo2、blood_pressure_* 等，也可自定义。"""

    # 指标名采用字符串而非枚举，以支持未来接入血糖、体温和厂商私有指标。
    metric: str = Field(min_length=1, max_length=64)#指标名称，例如 heart_rate
    value: float                                    #数值，例如 132
    unit: str = Field(min_length=1, max_length=20)  #单位，例如 bpm
    measured_at: datetime                           #测量时间  
    source: str = Field(min_length=1, max_length=50)#数据来源，例如 watch


class TrajectoryPoint(BaseModel):
    """一次定位采样点；轨迹异常规则可基于这些点扩展。"""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0)
    recorded_at: datetime


class HealthSnapshot(BaseModel):
    """手表、iPhone 或云端汇集的一次健康与轨迹快照。"""

    # 一次上报包含的多条生命体征，限制数量可防止异常大请求。
    readings: list[HealthReading] = Field(min_length=1, max_length=200)
    trajectory: list[TrajectoryPoint] = Field(default_factory=list, max_length=500)
    has_suspected_fall: bool = False


class HealthFinding(BaseModel):
    """一条规则发现的异常；多个发现将被 Agent 汇总为一份报告。"""

    metric: str
    risk_level: RiskLevel
    reason: str
    evidence: Evidence


class ConfirmationRequest(BaseModel):
    """监护人对通知或报警操作进行明确确认时提交的请求。"""

    request_id: str
    device_id: int = Field(gt=0)
    action: str
    confirmed_by: str = Field(min_length=1, max_length=50)


class AuditRecord(BaseModel):
    """已经确认并执行的高风险操作记录。"""

    request_id: str
    device_id: int
    action: str
    actor: str
    created_at: datetime
    metadata: dict[str, Any] = {}
