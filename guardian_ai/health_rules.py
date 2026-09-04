from typing import Protocol

from .models import Evidence, HealthFinding, HealthReading, HealthSnapshot, RiskLevel


class HealthRule(Protocol):
    """新增能力只需实现 evaluate，不必修改 Agent 主循环。"""

    # 注册名必须唯一，例如 glucose、temperature 或 sleep。
    name: str

    # 输入完整健康快照，返回零条或多条异常发现。
    def evaluate(self, snapshot: HealthSnapshot) -> list[HealthFinding]: ...


class ThresholdRule:
    """通用上下限规则，适用于心率、血氧、血压等数值型指标。"""

    def __init__(self, metric: str, low: float | None, high: float | None,
                 level: RiskLevel, name: str) -> None:
        # low/high 为 None 表示不设置这一侧阈值，例如血氧只设置下限。
        self.metric, self.low, self.high, self.level, self.name = metric, low, high, level, name

    def evaluate(self, snapshot: HealthSnapshot) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        # 同一快照可能包含多次相同指标读数，逐条分析并保留所有异常证据。
        for reading in snapshot.readings:
            # 该规则只处理与自己指标名相同的读数。
            if reading.metric != self.metric:
                continue
            # 只要低于下限或高于上限，即视为异常。
            abnormal = ((self.low is not None and reading.value < self.low) or
                        (self.high is not None and reading.value > self.high))
            if abnormal:
                # 生成可读范围，None 使用无穷符号表示没有这侧限制。
                limit = f"{self.low if self.low is not None else '-∞'}–{self.high if self.high is not None else '∞'}"
                findings.append(HealthFinding(
                    metric=reading.metric, risk_level=self.level,
                    reason=f"{reading.metric} 为 {reading.value}{reading.unit}，超出预警范围 {limit}",
                    evidence=Evidence(source=reading.source, observed_at=reading.measured_at,
                                      detail=f"{reading.metric}={reading.value}{reading.unit}"),
                ))
        return findings


class FallRule:
    """疑似跌倒属于紧急事件，直接输出 critical，不能等待云端模型判断。"""

    name = "fall"

    def evaluate(self, snapshot: HealthSnapshot) -> list[HealthFinding]:
        # 未上报跌倒事件时，该规则不产生任何发现。
        if not snapshot.has_suspected_fall:
            return []
        # 跌倒事件使用快照中最新健康读数的时间作为事件近似时间。
        latest = max((r.measured_at for r in snapshot.readings), default=None)
        if latest is None:
            return []
        return [HealthFinding(metric="fall", risk_level=RiskLevel.CRITICAL,
                              reason="设备检测到疑似跌倒，不能等待云端确认",
                              evidence=Evidence(source="wearable", observed_at=latest,
                                                detail="suspected_fall=true"))]


class HealthRuleEngine:
    """规则注册表与执行器，负责把每个独立规则组合成可扩展能力。"""

    def __init__(self, rules: list[HealthRule] | None = None) -> None:
        self._rules: dict[str, HealthRule] = {}
        # 初始化时逐个注册，复用 register 的唯一命名规则。
        for rule in rules or []:
            self.register(rule)

    def register(self, rule: HealthRule) -> None:
        """以规则名注册/替换新能力，例如血糖、体温、睡眠或厂家私有传感器。"""
        self._rules[rule.name] = rule

    def evaluate(self, snapshot: HealthSnapshot) -> list[HealthFinding]:
        """依次执行所有已注册规则，并汇总每条规则发现的风险。"""
        all_findings: list[HealthFinding] = []
        for rule in self._rules.values():
            all_findings.extend(rule.evaluate(snapshot))
        return all_findings

    @property
    def capabilities(self) -> list[str]:
        """返回已注册规则名，供 iOS 或管理后台展示。"""
        return sorted(self._rules)


def default_health_engine() -> HealthRuleEngine:
    # 阈值为演示预警规则；生产版需按年龄、病史、医嘱和医疗合规要求个体化配置。
    # 这里定义演示版默认规则集合；生产版可从数据库读取每位用户的个体化配置。
    return HealthRuleEngine([
        FallRule(),
        ThresholdRule("heart_rate", 40, 120, RiskLevel.HIGH, "heart-rate"),
        ThresholdRule("spo2", 90, None, RiskLevel.HIGH, "blood-oxygen"),
        ThresholdRule("blood_pressure_systolic", 90, 180, RiskLevel.MEDIUM, "blood-pressure-systolic"),
        ThresholdRule("blood_pressure_diastolic", 60, 120, RiskLevel.MEDIUM, "blood-pressure-diastolic"),
        ThresholdRule("body_temperature",35.0,37.5,RiskLevel.MEDIUM,"body-temperature"),
    ])
