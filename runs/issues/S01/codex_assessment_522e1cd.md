# S01提交522e1cd复验（2026-10-29）

结论：RETURN_FOR_REWORK，暂不放行S02。上轮毛利率零/负基期、重述PROVISIONAL、低基数确认、逐字段期间及多数质量边界已修复，但组合信号仍有Q06绕过路径；此外本轮发现SG02的冻结机器阈值与文字定义存在单位矛盾，须在正式指标计算前消除。

## 已核实

GitHub提交522e1cd38fa811c5bfda8b577c26492d74fbca7d存在。规则SHA256仍为c76d04615669788dddc17425de6afd78ec55be4b7f20bbd75b7322e777858f7e，Git blob与326ecac相同。3份输入指纹、manifest全匹配。只调用纯函数及load_rows，没有运行会写原产物的main。

16个既有合成测试复现16/16 PASS；匿名重算L2=290（另706 NOT_SHORTLISTED、58 HOLD_FOR_DATA），M01=565 OK、386 PROVISIONAL、44 NOT_COMPARABLE、58 HOLD、1 MISSING。这些验证修复进展，不构成公司改善名单。

## 剩余阻断1：SG07缺少第二输入质量并集

signals_of中SG07以M08>=0.8且M09>0为条件，但fired.flags仅复制M08.flags；未把M09.flags并入。M09状态允许PROVISIONAL，因此当M08正常而同比基期现金流涉及重述时，SG07依然以无Q06、confirmed=True进入L2维度。

纯函数补测：M08=1/OK/无标记，M09=1000万元/PROVISIONAL/Q06，SG07仍返回flags=[]、confirmed=True。全池当前匿名复算有18个实际信号漏传M09的Q06。事后“两干净维度”检验仍读同一个已丢标记的fired.flags，不能发现这类输入层漏传。

luna_worker独立只读复核得到相同18条漏Q06；仅修正这18条时当前L2标签翻转0，但CASH维度仍被错标为干净。另复核出同路径Q05漏传：m08未读取原始OCF/NPP输入的low_base标记；22条实际SG07输入带Q05却被漏掉，其中14条M08无Q06。按冻结Q05政策剔除这类未经确认的SG07，有1条现有L2标签翻转。纯函数给M08原始输入LOW_BASE_PROFIT也仍返回OK、无Q05，问题可复现。

修复：每个指标先从全部原始依赖传播Q05/Q06，每个复合信号再明确所有必需指标，先合并其flags及状态，再作L1/L2资格判定；SG07同时用M08和M09的质量信息。M08没有绝对额确认口径，输入Q05须进入NO_CONFIRM_INPUT而非自动确认为干净。补测必须包含“当前M08无重述、基期导致M09有Q06”和“M08输入带低基数”，不能只测试同指标或所有输入同时重述。事后检验应从原始metric结果重新取依赖标记，不能只读fired自报flags。

## 剩余阻断2：SG02的5pp与0.05pp矛盾

这是一处本轮才指出的既存定义错误，先前未识别，不是执行者本次改动阈值。

M03实现返回(本季同比-上季同比)*100，单位pp。冻结JSON的SG02却是threshold=0.05、unit=pp，同时note和metric_formulas/threshold_rationale写加速>=5pp。当前代码SIGNALS同样以0.05作阈值，实际等于0.05个百分点，比5个百分点小100倍。

补测M03=1pp即触发SG02（按文字5pp定义不应触发）；当前匿名干跑有107个SG02触发的加速度低于5pp。该数仅证明定义不一致，不用于决定应该筛出多少家。

修复：统一M03数值单位、JSON机器阈值、代码与文字说明。若采用既定文字意图5pp，机器pp单位阈值应为5.0；若采用ratio差0.05，则M03不可再乘100且所有单位/比较须对应。由于冻结文件存在内部矛盾，保留v1并登记单位勘误/新规则版本及输入指纹，再全池匿名复算；不是按命中率调阈值。

## 剩余边界：UNKNOWN非合并口径未拦截

_inputs仅将PARENT_ONLY/NON_CONSOLIDATED列为BAD_SCOPES，未拦截非LEGACY_SNAPSHOT的UNKNOWN。冻结Q12要求UNKNOWN且非旧快照也不能进主筛选。补测scope=UNKNOWN、status=EXTRACTED的M01返回OK且无Q12。修复为非旧快照必须明确CONSOLIDATED；旧快照UNKNOWN按Q07单列例外。补UNKNOWN用例，不只测试PARENT_ONLY。

## 返工范围

不重采资料、不改S00。保留已修复部分，只修组合质量传播、SG02单位一致性及UNKNOWN口径边界。新增原反例测试后复算，既有16测试PASS仍保留。阈值偏松和维度相关性可按既定研究版本计划处理，不作为此次退回理由；上述执行/定义缺陷不能留到S04。

复算脚本codex_audit_522e1cd.py及结果JSON已留存。本次未改远端调度与WorkBuddy产物，S02继续等待。

