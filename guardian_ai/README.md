# Guardian AI V0.1

一个安全优先、可扩展的守护 Agent 原型：自动查询只读设备数据，依据确定性规则生成结构化风险报告；通知和报警只能在监护人确认后执行，并有幂等与审计保护。

## 健康数据扩展

`POST /v1/devices/{device_id}/health-analysis` 接收任意 `metric` 健康指标。内置规则覆盖心率、血氧（`spo2`）、收缩压、舒张压和疑似跌倒；轨迹点也已纳入数据契约。新增血糖、体温、睡眠或厂家私有传感器时，实现 `HealthRule.evaluate()` 后调用 `health_engine.register()` 即可，无需改动 Agent。

## 接入 ED Watch 真实数据

复制 `.env.example` 的变量到本机 `.env`，填入仅供服务端使用的 `ED_WATCH_API_TOKEN`。随后调用 `POST /v1/devices/{device_id}/sync-health-analysis`，服务端会调用 `Device/HealthInfo` 并将 `HeartRate`、`BloodOxygen`、`BloodMax`、`BloodMin` 与 `Temperature` 转换为统一健康读数后进行风险分析。设备返回的 `0` 视为“尚无有效测量”，不会被当作健康数据。`BloodSuger` 的实际单位需先与设备协议确认，当前仅保留原始读数，不执行阈值判断。

## 返回数据文件

每次风险分析、同步健康分析和人工确认成功后，返回结果会追加到 `data/guardian_responses/responses-YYYY-MM-DD.jsonl`。每一行是一条 JSON 记录，包含记录时间、接口路径和返回数据。该目录可能包含健康信息，已被 Git 忽略。

## 第 4 周：大模型结构化解释

调用 `POST /v1/devices/{device_id}/ai-health-explanation`。它先执行本地健康规则，再生成 `risk_level`、`summary`、`reasons` 和 `requires_human_confirmation` 的固定 JSON。默认 `GUARDIAN_LLM_MODE=mock`，可离线学习和测试；设置为 `openai` 后，需要在 `.env` 中配置服务端专用的 `OPENAI_API_KEY` 与 `OPENAI_MODEL`。模型只能解释规则结果，不能改变风险等级或绕过人工确认。

## 第 4 周：日志 AI 分析器 V0.1

调用 `POST /v1/logs/analyze`，请求体传入 `log_text` 和可选的 `source`。服务先识别 `[时间] ERROR:消息`、`时间 [ERROR] 消息` 与无前缀的错误文本，再生成固定的 `error_type`、`key_evidence`、`possible_causes`、`check_steps` 与 `danger_warnings`。默认 mock 模式可分析当前 `data/Error.log` 中的 Pydantic 校验错误和 JSON 格式错误；openai 模式使用同一份 JSON Schema 输出结构。

## 启动

```bash
uvicorn guardian_ai.main:app --reload
pytest -q
```

访问 `http://127.0.0.1:8000/docs` 查看接口。该版本使用模拟数据，尚未连接真实设备、数据库或大模型。
