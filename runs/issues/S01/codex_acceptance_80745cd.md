# S01最终复验结论（提交80745cd，2026-10-29）

结论：ACCEPTED_WITH_LIMITS，支持正式验收S01，并放行S02全池指标计算与口径检查。S02必须使用冻结规则S01_SCREEN_RULES_V2，不能继续用v1的SG02错误单位，也不得直接进入S03名单筛选、业务深研或估值。

已核GitHub提交80745cdc4e3f521b14b1ad7d716d05497914ea4d存在。v1 SHA256仍为c76d04615669788dddc17425de6afd78ec55be4b7f20bbd75b7322e777858f7e；v2仍为ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85。三份研究输入指纹、manifest全部输出哈希匹配。

本次只读导入函数复核，没有运行会覆盖原产物的main：
- 结构检查无FAIL，23个合成测试全部PASS。
- 1054家公司逐家按冻结v2重算匿名指标/信号；独立按规则主指标及SG07复合依赖推导期待flags，不以执行器SIGNAL_DEPS自证：质量标记漏传0、普通OK带Q06/Q12为0、缺少两干净维度而判L2候选为0。
- SG09共203个触发，M07依赖已登记并正确传播Q05/Q06。
- 故障注入：临时在内存移除SG09依赖后，C16确实FAIL，signal_flags返回None而非空集；随即恢复内存状态，不修改任何文件。
- 匿名重算L1=841 OBSERVE_QUEUE、138 RISK_WATCH、75 NO_SIGNAL；L2=280 SHORTLIST_CANDIDATE、716 NOT_SHORTLISTED、58 HOLD_FOR_DATA；SG01/SG02并集=659，与最新交接一致。以上为规则实现一致性验证，不作实际公司改善结论或名单。

上轮依赖表遗漏已关闭。此前修复的SG07全部依赖并集、M08低基数、UNKNOWN非旧快照排除、毛利率pp边界、重述PROVISIONAL及单位勘误继续有效。

保留限制：阈值为研究假设；MARGIN/PROFIT维度相关性尚未解决；2026Q3截面不完整；S00的HOLD/PROVISIONAL与缺失限制继续适用。S02必须逐格输出metric_status、quality_flags、期间及来源，不得将PROVISIONAL混入普通OK。后续若改变收紧政策，另立v3并全池重算、保留版本差异，不按目标家数调整。

本次技术复核不等于全池业务证据独立验收。只保存本地复核记录，未修改远端调度/关闭issue；可据此将S01正式验收并把S02改为READY。

