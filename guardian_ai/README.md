# Guardian AI V0.1

一个安全优先、可扩展的守护 Agent 原型：自动查询只读设备数据，依据确定性规则生成结构化风险报告；通知和报警只能在监护人确认后执行，并有幂等与审计保护。

## 健康数据扩展

`POST /v1/devices/{device_id}/health-analysis` 接收任意 `metric` 健康指标。内置规则覆盖心率、血氧（`spo2`）、收缩压、舒张压和疑似跌倒；轨迹点也已纳入数据契约。新增血糖、体温、睡眠或厂家私有传感器时，实现 `HealthRule.evaluate()` 后调用 `health_engine.register()` 即可，无需改动 Agent。

## 接入 ED Watch 真实数据

复制 `.env.example` 的变量到本机 `.env`，填入仅供服务端使用的 `ED_WATCH_API_TOKEN`。随后调用 `POST /v1/devices/{device_id}/sync-health-analysis`，服务端会调用 `Device/HealthInfo` 并将 `HeartRate`、`BloodOxygen`、`BloodMax`、`BloodMin` 与 `Temperature` 转换为统一健康读数后进行风险分析。设备返回的 `0` 视为“尚无有效测量”，不会被当作健康数据。`BloodSuger` 的实际单位需先与设备协议确认，当前仅保留原始读数，不执行阈值判断。

## 启动

```bash
uvicorn guardian_ai.main:app --reload
pytest -q
```

访问 `http://127.0.0.1:8000/docs` 查看接口。该版本使用模拟数据，尚未连接真实设备、数据库或大模型。
