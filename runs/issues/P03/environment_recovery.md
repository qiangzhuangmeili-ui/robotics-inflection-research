# P03：环境恢复与入口边界

执行日：2026-10-26。执行/自检：Codex，SELF_CHECK，不是业务独立审计。

## 实测故障和恢复

- 本机 `127.0.0.1:8774/toolbox` 初始拒绝连接，服务未运行；不是公司没有资料。
- 默认 `python`/`py` 指向WindowsApps不可执行别名。使用既有 `D:/StockResearchLab/AKShare/.venv/Scripts/python.exe`，未升级、重建或修改AKShare环境。
- 先尝试隐藏Start-Process，进程未持续存活；本轮最终用持久执行会话启动 `tools/p03_local_service.py`。该脚本导入既有workbench/app.py的Handler，只监听127.0.0.1，不打开浏览器、不改旧源文件。页面与catalog分别HTTP 200，旧工作台沪深样本财务接口200。
- 服务在执行会话中实测可用，不承诺会话退出后常驻。重新启动可使用原来的 `D:/StockResearchLab/AKShare/启动-AKShare试用.cmd`，或在正式目录运行 `& 'D:/StockResearchLab/AKShare/.venv/Scripts/python.exe' tools/p03_local_service.py`。
- 沙箱内网络请求出现ProxyError，而同一已授权请求在允许网络的执行环境成功。这是执行环境差异，不读取或改动系统代理配置，不要求用户切换代理。

## 北交所必须走独立路由

旧app.py的stock_code和finance_features.py的validate仅放行沪深前缀；北交所920207在旧本机财务入口实测400。未把沪深成功当作北交所覆盖，也未修改旧工作台校验。后续P05复用 `tools/source_access.py`：证券主体显式传入 `SH:688218`、`SZ:002031`、`BJ:920207`，不从代码前缀猜交易所。

## 已验证的最小样本

| 路径 | 沪688218 | 深002031 | 北920207 |
|---|---|---|---|
| 新浪利润表直连（非官方结构化源） | 20260630一报告期 | 同左 | 同左 |
| 巨潮年报目录 | 2条：全文/摘要 | 2条：全文/摘要 | 2条：全文/摘要 |
| 既有官方年报PDF | 巨潮200，哈希匹配 | 巨潮200，哈希匹配 | 北交所200，哈希匹配 |
| 旧本机财务接口 | 200 | 200 | 400，应用限制 |

只证明这三份样本及所列接口在取件时点可达。未证明所有公司、所有报告期、全部财务字段覆盖，也不代表业务证据验收。

## 公告索引修正

初始三样本带searchkey=2025的查询均HTTP200但0条；调整后已知报告正常返回。沪使用column=sse；深与本次北交所样本使用column=szse、空searchkey、category_ndbg_szsh。尝试未经支持的bjse列返回500，已记录为无效路由，不进入生产路由。不能把这些空结果写成未披露。adapter_smoke.json记录最终适配器的三市场实际执行结果。

## 复现

在正式目录中，以既有AKShare Python执行：

```powershell
& 'D:/StockResearchLab/AKShare/.venv/Scripts/python.exe' -X utf8 tools/p03_probe.py public
& 'D:/StockResearchLab/AKShare/.venv/Scripts/python.exe' -X utf8 tools/p03_probe.py indexes
& 'D:/StockResearchLab/AKShare/.venv/Scripts/python.exe' -X utf8 tools/p03_probe.py workbench
& 'D:/StockResearchLab/AKShare/.venv/Scripts/python.exe' -X utf8 tools/p03_adapter_smoke.py
& 'D:/StockResearchLab/AKShare/.venv/Scripts/python.exe' -X utf8 tools/test_source_access.py
```

probe_records.json中的初始诊断请求由p03_probe.probe函数经一次性Python命令执行；后续indexes/workbench模式已将对应最终请求固化。不要为了重放错误请求反复撞同源。PDF缓存位于sources/p03_probes，未上传GitHub。

## 熔断和剩余任务

source_circuit_policy.json与source_access.py定义并实现有限重试、按源熔断及断点状态。无效JSON、HTML冒充PDF、主体错配、已知报告空目录不能记为成功。两次运输层失败停止该源，401/403/429立即停止，冷却900秒后只允许已知正常样本复探。404仅记文档问题，不扩大为全源故障。模拟故障测试不访问1054家公司，只验证1054次排队调用在熔断后不会产生额外HTTP请求。

P04冻结单位/字段；P05实现多报告期、分页、字段标准化和采集断点；P06归档容量规则；P07十家公司校准。P03不启动全池、不提业务结论、不生成逐家公司手补请求。P05不得绕回旧工作台的北交所拒绝路由。
