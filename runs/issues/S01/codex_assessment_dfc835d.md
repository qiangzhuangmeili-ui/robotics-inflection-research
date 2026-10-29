# S01提交dfc835d复验（2026-10-29）

结论：暂不放行S02；上轮三项修复已成立，但依赖表重构新漏SG09，须局部补齐再验。不扩大为重采、重算S00或调整其他阈值。

已核GitHub提交dfc835d05503ab94a2cd2d4c34fe708ac5e5758e存在。

## 已通过

- v1 SHA256保持c76d04615669788dddc17425de6afd78ec55be4b7f20bbd75b7322e777858f7e。
- v1/v2真实JSON递归差异仅change_log、frozen_at、rules_version、signals[1].threshold、signals[1].note。SG02机器阈值5.0pp与文字一致。
- 3输入指纹及manifest所有输出哈希匹配。
- 只读运行synthetic_tests(rules)，21/21既有合成测试PASS；未执行会写原产物的main。
- 匿名全池重算L1=841观察/138风险/75无信号，L2=281候选/715未入/58 HOLD，SG02=415，与交付一致。上述仅为执行一致性核验，不是公司改善结论。
- SG07依赖标记并集、m08低基数读取、非旧快照UNKNOWN口径排除的实现已修复。

## 唯一剩余阻断：SG09未登记依赖

SIGNAL_DEPS中只有SG01—SG08，遗漏SG09；冻结规则明确SG09依赖M07。signal_flags使用SIGNAL_DEPS.get(sid,[])，遇遗漏返回空集。

signals_of生成SG09时，deps字段使用.get(id,[metric])得到M07，但最后赋flags时调用signal_flags又变为空集；confirm_low_base因此认为无低基数，confirmed=True。layers也从同一缺漏表重取依赖，仍为空集。自检signal_flags_missing_dep以同一空集为期待值，自然报0。

本次独立核验从规则的主metric补足依赖，发现：SG09共203个触发，106条缺失一个或多个输入标记；其中74条漏Q06、49条漏Q05（有交集，不能相加）。仅移除Q06错误贡献时当前匿名L2不足两维计数未增加，但信号元数据与政策执行仍不正确，不能据此忽略。

合成反例：将M07设为40%/PROVISIONAL/Q06，SG09依然输出flags=[]、confirmed=True、NO_LOW_BASE。按冻结政策Q06信号可进L1但不得贡献L2。

## 修复与复验要求

1. 补SIGNAL_DEPS['SG09']=['M07']。
2. 增加集合等式断言：冻结rules.signals所有ID必须精确匹配依赖表，不得缺项；各依赖指标必须存在。
3. 对所有信号逐项注入Q05/Q06/HOLD/排除口径作质量传播测试，而非只测SG07。缺依赖必须报错，不允许默认空集放行。
4. 政策不变量检查应由规则主指标+显式复合依赖独立生成期待集合；不能只用执行器同一依赖表验证自身。
5. 匿名重算、刷新self_check/review/manifest即可；保持v1和已正确勘误v2不改，不按候选数调门槛。

本次只读复验，未修改远端调度或WorkBuddy交付。S02继续WAITING_DEPENDENCIES。

