# S02 接入复核与守卫交接（2026-10-29）

本轮接续 WorkBuddy 的 `e41f61d` 修复版接手状态。数据仍是已交付的 v2；本轮只修接入、复现和观察保护。正式数据与控制文件没有被覆盖，S03 未实际执行。

## 完成结果

- 计算器绑定真正载入的CSV/payload，并校验其已登记内容哈希；可读取已知同内容副本和`.csv.gz`，压缩件只在明确输出目录中解压缓存。
- v2每次重跑均自动应用已锁SHA的L0补丁，不会再遗留3家MIXED。v1明确显示补丁不适用；v2未应用补丁即失败关闭。
- 新计算清单登记calculator、formula、L0、上游A03及重抽计划哈希。生产代码已存本地提交 `d72d4d5`；`reproduction_manifest.json` 将它与canonical两张CSV的精确字节重现关联。历史canonical manifest保留不追改。
- 360份PDF的实际二进制SHA复验通过；19条原页金额/单位存在性与物理页位置检查通过（不冒称全量独立财务字段抽取）。新输入的28项政策结构检查和23项合成测试通过；11组接入测试、17项守卫测试、15项契约校验通过。
- Reasonix独立会话首轮退回3项，补修后复审结论 `PASS_TECHNICAL_WITH_LIMITS`；它在自己目录分别用CSV副本和gzip重跑，12,648格指标与1054家公司汇总均与canonical逐字节相同。完整意见及其未独立验证边界保留在reasonix目录。
- Q05 readiness支持显式绝对额确认；它不替代S01.signals_of/confirm_low_base/layers，也不能用于否决SG06等冻结允许的绝对额路径。

## 21家待核与下一步

10家EVALUABLE、8家W5、3家W9逐家写入protected_21.csv。开放覆盖问题未解决时，10家EVALUABLE原始NO_SIGNAL转待复核；W5无触发仍观察；W9保留数据/范围复核。PROVISIONAL/HOLD不得混入干净维度。不为筛选数量调阈值。

S03第一步必须实际调用tools/s03_input_gate.py的load_gate_inputs，并对已有L0/L1路由调用protect_existing_route；保存实际消费验证记录后才可做冻结L1技术宽筛。当前consumer_verified仍false，本轮没有生成S03名单。

## 复现

正式输入/指标仍在 runs/issues/S02/remediation_20261029/。执行`reproduce_committed.py`会自行从归档gzip产生隔离CSV副本，然后分别重算；不再依赖Reasonix临时输入目录。原公式文件存在已核实的Git LF/工作副本CRLF差异，来源清单同时记录两种哈希与纯换行等价性，未改写旧文件。

复跑接入测试：`python runs/issues/S02/recheck_20261029/integration/test_s02_integration.py`。
复跑守卫测试：`python -m unittest discover -s runs/issues/S02/recheck_20261029/gates -p test_s03_input_gate.py -v`。

## 发布断点

自动审批拒绝了直接推送GitHub main，理由为未获明确共享默认分支写入授权。因此远端控制仍是S02待复核、S03锁定。本包中的acceptance_recommendation.json是技术验收建议，proposed_control_updates.json是可审查但未应用的状态更新。不得把本地提交或Drive交付当作远端已更新，也不通过其他代理绕过该审批。获得明确授权后还须重读在线控制版本，冲突则先重读，不覆盖其他执行者。

代码覆盖包以现有修复版/e41f61d为基线；如本机代码已有其他修改，先比较哈希与差异，不盲目覆盖。包不包含原PDF、密钥、账号配置或大表测试副本。
