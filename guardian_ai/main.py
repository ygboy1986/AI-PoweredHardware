from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from .agent import GuardianRiskAgent
from .ed_watch_repository import EdWatchAPIError, EdWatchHealthRepository
from .health_rules import default_health_engine
from .llm_explainer import ExplanationError, get_health_explainer
from .log_analyzer import LogAIAnalyzer
from .models import (AuditRecord, ConfirmationRequest, ExplainedRiskReport,
                     HealthSnapshot, LogAnalysisRequest, LogAnalysisResponse)
from .response_store import ResponseStore
from .tools import DemoDeviceRepository, build_read_only_tools

# 创建 FastAPI 应用。启动 uvicorn 后，/docs 会自动生成接口调试页面。
app = FastAPI(title="Guardian AI", version="0.1.0")

# 注册默认健康规则：心率、血氧、血压和疑似跌倒。
# 新增健康能力时，可在 health_rules.py 中创建规则后注册到此引擎。
# 健康规则引擎--规则集合
health_engine = default_health_engine()#None

# 当前使用内存中的模拟设备数据，方便先完成端到端联调。
# 生产环境应替换为带鉴权的设备、健康和位置业务服务。
# 创建的分析对象
agent = GuardianRiskAgent(build_read_only_tools(DemoDeviceRepository()), health_engine)

# 演示版审计存储：服务重启后会清空。
# 生产环境应保存到数据库，且记录操作者、时间、设备与请求 ID。
audit_log: list[AuditRecord] = []

# 幂等键集合：防止用户连点或网络重试造成重复通知/重复报警。
# 键由一次分析请求 ID 和写操作名称共同组成。
executed_actions: set[tuple[str, str]] = set()

# 接口返回结果按天追加写入 data/guardian_responses/，供后续分析和复盘。
response_store = ResponseStore()
log_ai_analyzer = LogAIAnalyzer()
MAX_LOG_FILE_BYTES = 1_000_000  # 演示版上限 1 MB，防止异常大文件耗尽服务内存。


@app.get("/health")
def health() -> dict[str, str]:
    """供 iOS、负载均衡或监控系统检测服务是否存活。"""
    return {"status": "ok"}


@app.post("/v1/logs/analyze")
def analyze_log(request: LogAnalysisRequest) -> LogAnalysisResponse:
    """第 4 周日志 AI 分析器：解析日志并返回固定 JSON 结论。"""
    response = log_ai_analyzer.analyze(request)
    response_store.append("/v1/logs/analyze", response)
    return response


@app.post("/v1/logs/upload")
async def upload_log(file: UploadFile = File(...)) -> LogAnalysisResponse:
    """上传 UTF-8 编码的 .log/.txt 文件，再复用日志 AI 分析流程。

    接口只保存结构化分析结果，不保存上传的原始日志文件。
    """
    filename = file.filename or "uploaded.log"
    if not filename.lower().endswith((".log", ".txt")):
        raise HTTPException(status_code=415, detail="仅支持 .log 或 .txt 日志文件")
    content = await file.read(MAX_LOG_FILE_BYTES + 1)
    if len(content) > MAX_LOG_FILE_BYTES:
        raise HTTPException(status_code=413, detail="日志文件不能超过 1 MB")
    try:
        # utf-8-sig 同时兼容 Windows 常见的 BOM 编码文本。
        log_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="日志文件必须使用 UTF-8 编码") from error

    response = log_ai_analyzer.analyze(LogAnalysisRequest(log_text=log_text, source=filename))
    response_store.append("/v1/logs/upload", response)
    return response


@app.post("/v1/devices/{device_id}/risk-report")
def risk_report(device_id: int):
    """演示接口：调用预置的只读设备工具，生成今日风险概览。"""
    report = agent.analyze_today(device_id)
    response_store.append("/v1/devices/{device_id}/risk-report", report)
    return report


@app.post("/v1/devices/{device_id}/health-analysis")
def health_analysis(device_id: int, snapshot: HealthSnapshot):
    """接收手表健康数据，执行规则分析并返回结构化风险报告。

    本接口只分析数据和提出建议；即使判定为高风险，也绝不自动执行
    通知或设备报警。写操作必须由监护人在 confirm_action 中明确确认。
    """
    report = agent.analyze_health(device_id, snapshot)
    response_store.append("/v1/devices/{device_id}/health-analysis", report)
    return report


#@app.post("/v1/devices/{device_id}/ai-health-explanation")
@app.post(
    "/v1/devices/{device_id}/ai-health-explanation",
    response_model=ExplainedRiskReport,
    responses={
        503: {
            "description": "健康规则引擎未配置",
        },
    },
)
def ai_health_explanation(device_id: int, snapshot: HealthSnapshot) -> ExplainedRiskReport:
    """先由本地规则判定风险，再由模型生成固定 JSON 格式的用户说明。"""
    report = agent.analyze_health(device_id, snapshot)
    try:
        explainer = get_health_explainer()
        explanation = explainer.explain(report)
        response = ExplainedRiskReport(
            risk_report=report, ai_explanation=explanation,
            ai_provider=explainer.provider_name, fallback_used=False,
        )
    except RuntimeError as error:
        raise HTTPException(
          status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
          detail=str(error),
        ) from error   
    except ExplanationError:
        # 模型无 Key、超时或格式异常时仍可交付安全的固定说明。
        from .llm_explainer import MockHealthExplainer
        explanation = MockHealthExplainer().explain(report)
        response = ExplainedRiskReport(
            risk_report=report, ai_explanation=explanation,
            ai_provider="mock_fallback", fallback_used=True,
        )
    response_store.append("/v1/devices/{device_id}/ai-health-explanation", response)
    return response


@app.post("/v1/devices/{device_id}/sync-health-analysis")
def sync_health_analysis(device_id: int):
    """从 ED Watch 的真实 `Device/HealthInfo` 接口拉取数据后立即执行规则分析。"""
    try:
        repository = EdWatchHealthRepository.from_environment()
        snapshot = repository.fetch_health_snapshot(device_id)
    except EdWatchAPIError as error:
        # Token、网络和设备同步异常不应导致 API 崩溃，也不向客户端泄露 Token。
        raise HTTPException(status_code=502, detail=str(error)) from error
    report = agent.analyze_health(device_id, snapshot)
    response_store.append("/v1/devices/{device_id}/sync-health-analysis", report)
    return report


@app.get("/v1/capabilities/health-rules")
def health_capabilities() -> dict[str, list[str]]:
    """让 iOS 或管理后台获取当前已启用的健康检测规则。"""
    return {"registered_rules": health_engine.capabilities}


@app.post("/v1/actions/confirm", status_code=201)
def confirm_action(request: ConfirmationRequest) -> AuditRecord:
    """执行高风险操作前的人工确认关卡，并写入审计记录。"""
    # 白名单限制：Agent 或客户端不能借此接口执行任意操作。
    if request.action not in {"send_guardian_notification", "start_device_alarm"}:
        raise HTTPException(400, "不支持或不需要确认的操作")

    # 同一个请求只能执行一次相同操作，避免网络重试造成重复通知。
    key = (request.request_id, request.action)
    if key in executed_actions:
        raise HTTPException(409, "该操作已执行；幂等保护已阻止重复通知")

    # 演示版只记录确认事实；生产版此处再调用通知服务或设备报警服务。
    executed_actions.add(key)
    record = AuditRecord(request_id=request.request_id, device_id=request.device_id,
                         action=request.action, actor=request.confirmed_by,
                         created_at=datetime.now(timezone.utc))
    audit_log.append(record)
    response_store.append("/v1/actions/confirm", record)
    return record


@app.get("/v1/audit")
def get_audit() -> list[AuditRecord]:
    """返回已确认的高风险操作，供监护人或管理员追溯。"""
    return audit_log
