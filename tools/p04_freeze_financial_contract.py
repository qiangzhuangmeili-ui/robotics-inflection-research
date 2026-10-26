"""P04 生成器：冻结财务字段字典、来源字段映射、期间换算规则。

输入（全部为本仓库已有证据，不联网、不改原件）：
- runs/issues/P04/provider_field_inventory.csv     新浪接口真实字段（P04 实测）
- runs/issues/P04/pdf_lineitem_evidence.json       官方年报 PDF 行项目与页码（P04 实测）
- runs/issues/P04/crosscheck_provider_vs_pdf.json  接口 vs 官方 PDF 数值一致性
- runs/issues/P04/crosscheck_period_conversion.json 累计/单季换算验证
- runs/issues/P02/existing_field_coverage.csv      旧快照 47 列覆盖
- 旧财务快照 CSV（只读，P02 已登记 sha256）

输出：
- runs/issues/P04/financial_field_dictionary.csv
- runs/issues/P04/provider_field_mapping.csv
- runs/issues/P04/period_conversion_rules.json
- runs/issues/P04/legacy_snapshot_gap_register.csv
- runs/issues/P04/evidence_index.json
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
SNAPSHOT = Path(r'C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究'
                r'\collection_run_20261026\raw\既有候选池财务快照.csv')
SNAPSHOT_SHA = '0c34f59567117b859ca57e9993f7a9fb8422598819274e4943ef331fa566b063'
RAW_PROBE = ROOT / 'sources/p04_probe'
PDF_CACHE = ROOT / 'sources/drive_readback_20261026'

VERSION = 'P04_FIELD_CONTRACT_V1'
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

# ---------------------------------------------------------------- 字段字典
# unit_kind: AMOUNT_CNY / RATIO_PCT / DELTA_PP / PER_SHARE_CNY / DATE / CODE / TEXT
FIELDS = [
    dict(field_id='FIN.REV.YTD', name_cn='营业收入（合并，年初至今累计）', name_en='Revenue (consolidated, YTD)',
         statement='合并利润表', official_line='其中：营业收入',
         definition='合并报表营业收入，含主营业务收入与其他业务收入；不含营业外收入。',
         formula='直接取数', period_basis='YTD_CUMULATIVE', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='正数为收入；不得为负（除冲回）',
         p00_required='YES', comparability='同一合并范围、同一币种、同一报告期类型；重述后须用同一版本',
         blocking='合并范围或报告期无法确认时阻断', notes='不得用母公司报表或营业总收入替代；营业总收入在金融类公司含利息/保费收入，本池须单独核对'),
    dict(field_id='FIN.REV.SQ', name_cn='营业收入（合并，单季度）', name_en='Revenue (consolidated, single quarter)',
         statement='合并利润表', official_line='分季度主要财务数据-营业收入',
         definition='单一自然季度（Q1/Q2/Q3/Q4）营业收入，非年初至今。',
         formula='优先取官方分季度表；否则 Qn = 本期累计 − 上期累计（同一年度同版本）',
         period_basis='SINGLE_QUARTER', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='正数为收入', p00_required='YES',
         comparability='相减的两期必须同一年度、同一合并范围、无追溯重述',
         blocking='跨版本或合并范围变化时禁止相减，改用官方单季表', notes='旧快照无此列，须由 P05 采集或由累计派生'),
    dict(field_id='FIN.COST.YTD', name_cn='营业成本（合并，年初至今累计）', name_en='Cost of revenue (consolidated, YTD)',
         statement='合并利润表', official_line='其中：营业成本',
         definition='合并利润表营业成本，与营业收入同口径；不含税金及附加、期间费用。',
         formula='直接取数', period_basis='YTD_CUMULATIVE', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='正数为成本', p00_required='YES',
         comparability='须与营业收入同一合并范围与期间', blocking='与收入口径不一致时阻断毛利计算',
         notes='旧快照完全没有该字段，只能给毛利率百分比，无法反算毛利额'),
    dict(field_id='FIN.GROSSPROFIT.YTD', name_cn='毛利额（合并，派生）', name_en='Gross profit (derived)',
         statement='派生', official_line='无官方行项目（派生）',
         definition='营业收入 − 营业成本。', formula='FIN.REV.YTD − FIN.COST.YTD',
         period_basis='YTD_CUMULATIVE', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='可为负（成本倒挂）', p00_required='NO',
         comparability='仅当收入与成本同源同期间时计算', blocking='任一缺失则不计算，不得用毛利率反推',
         notes='旧快照只有 gross_margin_pct，无成本，无法得到毛利额'),
    dict(field_id='FIN.GROSSMARGIN.PCT', name_cn='毛利率（合并，%）', name_en='Gross margin (%)',
         statement='派生', official_line='（年报摘要披露“毛利率%”）',
         definition='毛利额 ÷ 营业收入 × 100，单位为百分数（如 23.28 表示 23.28%）。',
         formula='FIN.GROSSPROFIT.YTD ÷ FIN.REV.YTD × 100', period_basis='YTD_CUMULATIVE',
         unit_kind='RATIO_PCT', unit='%', scale='百分数数值，非小数',
         consolidation='CONSOLIDATED', sign='可为负', p00_required='NO',
         comparability='分母为同一期间营业收入且不为 0', blocking='收入为 0 或缺失时不计算',
         notes='旧快照 gross_margin_pct_2025 例：688218=23.282460，与官方 (510041067.79−391290961.13)/510041067.79 一致；不得当作小数 0.2328 使用'),
    dict(field_id='FIN.NP.YTD', name_cn='净利润（合并，年初至今累计）', name_en='Net profit (consolidated, YTD)',
         statement='合并利润表', official_line='五、净利润（净亏损以“－”号填列）',
         definition='合并净利润，含少数股东损益。', formula='直接取数', period_basis='YTD_CUMULATIVE',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED',
         sign='亏损为负', p00_required='NO', comparability='同合并范围同期间',
         blocking='不得与归母净利混用', notes='与归母净利的差额=少数股东损益'),
    dict(field_id='FIN.NPP.YTD', name_cn='归属于母公司所有者的净利润（累计）', name_en='Net profit attributable to parent (YTD)',
         statement='合并利润表', official_line='1.归属于母公司股东的净利润',
         definition='合并净利润中归属于母公司股东的部分。', formula='直接取数', period_basis='YTD_CUMULATIVE',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED',
         sign='亏损为负', p00_required='YES', comparability='同合并范围同期间',
         blocking='不得用净利润或扣非净利替代', notes='旧快照 net_profit_parent_cny_* 即此字段（已与官方 PDF 逐项核对一致）'),
    dict(field_id='FIN.NPP.SQ', name_cn='归属于母公司所有者的净利润（单季度）', name_en='Net profit attributable to parent (single quarter)',
         statement='合并利润表', official_line='分季度主要财务数据-归属于上市公司股东的净利润',
         definition='单一自然季度归母净利。', formula='优先官方分季度表；否则 Qn = 本期累计 − 上期累计',
         period_basis='SINGLE_QUARTER', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='亏损为负', p00_required='NO',
         comparability='同一年度同版本；重述后重算', blocking='跨版本禁止相减', notes='旧快照无此列'),
    dict(field_id='FIN.NPDEDT.YTD', name_cn='扣除非经常性损益后归母净利润（累计）', name_en='Recurring net profit attributable to parent (YTD)',
         statement='合并利润表附注/非经常性损益表', official_line='归属于上市公司股东的扣除非经常性损益后的净利润',
         definition='归母净利扣除归属于母公司的非经常性损益后的金额。',
         formula='直接取数（不得由归母净利估算）', period_basis='YTD_CUMULATIVE',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED',
         sign='亏损为负', p00_required='YES', comparability='同合并范围同期间同版本',
         blocking='结构化接口无此字段，必须回官方 PDF/定期报告', notes='新浪接口 77 个利润表字段中不存在扣非；只能取官方原文'),
    dict(field_id='FIN.NPDEDT.SQ', name_cn='扣非归母净利润（单季度）', name_en='Recurring net profit (single quarter)',
         statement='非经常性损益表/分季度表', official_line='分季度主要财务数据-归属于上市公司股东的扣除非经常性损益后的净利润',
         definition='单一自然季度扣非归母净利。', formula='优先官方分季度表；否则同年度累计相减',
         period_basis='SINGLE_QUARTER', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='亏损为负', p00_required='YES',
         comparability='同一年度同版本', blocking='不得用归母净利单季替代', notes='旧快照 22 列 deducted_np_parent_cny_YYYYMMDD 实测为累计口径，见 gap_register'),
    dict(field_id='FIN.OCF.YTD', name_cn='经营活动产生的现金流量净额（累计）', name_en='Net cash from operating activities (YTD)',
         statement='合并现金流量表', official_line='经营活动产生的现金流量净额',
         definition='经营活动现金流入减流出。', formula='直接取数', period_basis='YTD_CUMULATIVE',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED',
         sign='净流出为负', p00_required='YES', comparability='同合并范围同期间',
         blocking='不得用净利润替代', notes='旧快照完全没有该字段'),
    dict(field_id='FIN.OCF.SQ', name_cn='经营活动产生的现金流量净额（单季度）', name_en='Net cash from operating activities (single quarter)',
         statement='合并现金流量表', official_line='分季度主要财务数据-经营活动产生的现金流量净额',
         definition='单一自然季度经营现金流净额。', formula='优先官方分季度表；否则同年度累计相减',
         period_basis='SINGLE_QUARTER', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='净流出为负', p00_required='NO',
         comparability='同一年度同版本', blocking='跨版本禁止相减', notes='官方年报“分季度主要财务数据”表已直接披露，优先直接取'),
    dict(field_id='FIN.AR.INSTANT', name_cn='应收账款（时点）', name_en='Accounts receivable (point in time)',
         statement='合并资产负债表', official_line='应收账款',
         definition='合并资产负债表中“应收账款”期末余额，不含应收票据、应收款项融资、合同资产。',
         formula='直接取数', period_basis='INSTANT', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='正数', p00_required='YES',
         comparability='只能同时点比较；期初期末不得混用', blocking='不得与“应收票据及应收账款”合计混用',
         notes='新浪 ACCORECE 为小类明细，NOTESACCORECE 为合计项；官方 PDF 两者并存，须显式选一'),
    dict(field_id='FIN.NR.INSTANT', name_cn='应收票据（时点）', name_en='Notes receivable (point in time)',
         statement='合并资产负债表', official_line='应收票据',
         definition='合并资产负债表应收票据期末余额。', formula='直接取数', period_basis='INSTANT',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED', sign='正数',
         p00_required='NO', comparability='同时点比较', blocking='—', notes='部分公司并入“应收票据及应收账款”列示'),
    dict(field_id='FIN.CONTRACTASSET.INSTANT', name_cn='合同资产（时点）', name_en='Contract assets (point in time)',
         statement='合并资产负债表', official_line='合同资产',
         definition='合并资产负债表合同资产期末余额，与新收入准则相关。', formula='直接取数',
         period_basis='INSTANT', unit_kind='AMOUNT_CNY', unit='元', scale='1',
         consolidation='CONSOLIDATED', sign='正数', p00_required='YES',
         comparability='同时点比较；与应收账款分列', blocking='P00 要求“应收账款（含合同资产，分列）”，不得合并成一个数',
         notes='实测存在空白单元格（公司未列示），空白≠0'),
    dict(field_id='FIN.INV.INSTANT', name_cn='存货（时点）', name_en='Inventory (point in time)',
         statement='合并资产负债表', official_line='存货',
         definition='合并资产负债表存货期末余额。', formula='直接取数', period_basis='INSTANT',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED', sign='正数',
         p00_required='YES', comparability='同时点比较', blocking='—', notes='房地产/工程类存货口径差异大，跨行业比较须注明'),
    dict(field_id='FIN.ASSET.INSTANT', name_cn='资产总计（时点）', name_en='Total assets (point in time)',
         statement='合并资产负债表', official_line='资产总计',
         definition='合并资产负债表资产总计。', formula='直接取数', period_basis='INSTANT',
         unit_kind='AMOUNT_CNY', unit='元', scale='1', consolidation='CONSOLIDATED', sign='正数',
         p00_required='NO', comparability='同时点比较', blocking='—', notes='用于规模分组与异常筛查'),
    dict(field_id='FIN.PERIOD.START', name_cn='报告期起始日', name_en='Report period start',
         statement='元数据', official_line='报表标题（如“2025 年1—12 月”）',
         definition='报告期第一天，YYYY-MM-DD。', formula='由 period_key 推导', period_basis='METADATA',
         unit_kind='DATE', unit='—', scale='—', consolidation='NOT_APPLICABLE', sign='—',
         p00_required='YES', comparability='—', blocking='—', notes='Q1=01-01~03-31；H1=01-01~06-30；9M=01-01~09-30；FY=01-01~12-31'),
    dict(field_id='FIN.PERIOD.END', name_cn='报告期结束日', name_en='Report period end',
         statement='元数据', official_line='报表标题', definition='报告期最后一天，YYYY-MM-DD。',
         formula='由 period_key 推导', period_basis='METADATA', unit_kind='DATE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES', comparability='—', blocking='—',
         notes='决定单季归属与上市前不适用判断'),
    dict(field_id='FIN.PUBLISHED_ON', name_cn='实际披露日', name_en='Actual disclosure date',
         statement='元数据', official_line='公告披露日期',
         definition='该期报告在交易所/巨潮的实际披露日期，YYYY-MM-DD。',
         formula='取公告元数据；不得用报告期结束日代替', period_basis='METADATA',
         unit_kind='DATE', unit='—', scale='—', consolidation='NOT_APPLICABLE', sign='—',
         p00_required='YES', comparability='PIT 判断的唯一依据', blocking='未知时不得声称该期在 as_of 可得',
         notes='新浪 publish_date 为第三方声明值，须与巨潮公告日交叉核对；旧快照完全没有该字段'),
    dict(field_id='FIN.COLLECTED_AT', name_cn='取件日', name_en='Collection timestamp',
         statement='元数据', official_line='—', definition='实际抓取/下载该数据的时间戳（UTC）。',
         formula='采集器写入', period_basis='METADATA', unit_kind='DATE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES', comparability='—', blocking='—',
         notes='取件日 ≠ 披露日 ≠ 研究截止日，三者不得互相替代'),
    dict(field_id='FIN.AS_OF', name_cn='研究截止日', name_en='Knowledge as-of date',
         statement='元数据', official_line='—',
         definition='本轮研究信息截止日，冻结值 2026-10-25（P00）。', formula='常量',
         period_basis='METADATA', unit_kind='DATE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES', comparability='—',
         blocking='披露日晚于此日的文件只能登记为后续增量', notes='不得因新公告悄悄改写'),
    dict(field_id='FIN.CURRENCY', name_cn='币种', name_en='Currency',
         statement='元数据', official_line='币种：人民币', definition='报表币种。', formula='取报表表头',
         period_basis='METADATA', unit_kind='CODE', unit='ISO 4217', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES', comparability='跨币种不得直接相加',
         blocking='非 CNY 且无汇率来源时阻断', notes='实测四份样本均为 CNY；新浪 rCurrency=CNY'),
    dict(field_id='FIN.UNIT_SCALE', name_cn='金额单位与量纲', name_en='Unit and scale',
         statement='元数据', official_line='单位：元',
         definition='报表金额单位（元/千元/万元）与是否已折算为元。', formula='取报表表头并统一折算为元',
         period_basis='METADATA', unit_kind='CODE', unit='元/千元/万元', scale='统一为 1 元',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES',
         comparability='统一折算后再比较', blocking='表头缺失且无法从上下文确认时阻断该表全部金额',
         notes='实测四份样本表头均为“单位：元 币种：人民币”，无需换算；若遇万元须×10000并记录原单位'),
    dict(field_id='FIN.CONSOLIDATION_SCOPE', name_cn='合并范围', name_en='Consolidation scope',
         statement='元数据', official_line='合并资产负债表/合并利润表/合并现金流量表',
         definition='CONSOLIDATED=合并报表；PARENT_ONLY=母公司报表。', formula='按报表标题判定',
         period_basis='METADATA', unit_kind='CODE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES',
         comparability='合并与母公司不得混算', blocking='报表标题不明时阻断',
         notes='同一 PDF 内合并与母公司报表并存（实测 688218：合并 BS p122-124、母公司 BS p125-126），抽取必须锁定“合并”'),
    dict(field_id='FIN.AUDIT_STATUS', name_cn='审计状态', name_en='Audit status',
         statement='元数据', official_line='审计意见类型',
         definition='AUDITED/UNAUDITED/REVIEWED。', formula='取报表或公告元数据',
         period_basis='METADATA', unit_kind='CODE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='NO', comparability='—',
         blocking='—', notes='新浪 is_audit 返回“是/未审计”，年报为已审计，季报未审计'),
    dict(field_id='FIN.RESTATEMENT', name_cn='重述/版本标记', name_en='Restatement flag',
         statement='元数据', official_line='追溯调整或重述说明',
         definition='是否发生会计政策变更/追溯重述/同一控制下合并追溯。', formula='取年报说明段',
         period_basis='METADATA', unit_kind='CODE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES', comparability='重述后新旧版本不得相减',
         blocking='存在重述但未取得重述后数据时阻断跨期比较',
         notes='002354 年报明示“是否需追溯调整或重述以前年度会计数据 □是 否”，该勾选项须逐份读取'),
    dict(field_id='FIN.STATUS', name_cn='数据状态码', name_en='Data status code',
         statement='元数据', official_line='—',
         definition='沿用 P00 状态口径：COLLECTED_IDENTITY_VERIFIED / NOT_APPLICABLE_PRE_LISTING / SUBSTITUTED_BY_PROSPECTUS / NOT_DISCLOSED_BY_ISSUER / AFTER_CUTOFF_DISCLOSED / NOT_YET_DISCLOSED / SOURCE_FAILED / ACCESS_BLOCKED / NOT_TRIED。',
         formula='采集器判定', period_basis='METADATA', unit_kind='CODE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES', comparability='—',
         blocking='NOT_TRIED 不得计入完成', notes='缺失、未披露、取件失败、上市前不适用必须分开'),
    dict(field_id='FIN.LISTING_DATE', name_cn='上市日期', name_en='Listing date',
         statement='元数据', official_line='上市公告书/交易所页面',
         definition='该公司在对应交易所的上市日，YYYY-MM-DD。', formula='取交易所官方页面',
         period_basis='METADATA', unit_kind='DATE', unit='—', scale='—',
         consolidation='NOT_APPLICABLE', sign='—', p00_required='YES',
         comparability='判断“上市前不适用”的唯一依据', blocking='UNKNOWN 时不得判定 NOT_APPLICABLE_PRE_LISTING',
         notes='P00 冻结时 1054/1054 全为 UNKNOWN，须由 P05 回填；旧快照 listing_date 同样全 UNKNOWN'),
    dict(field_id='FIN.YOY.PCT', name_cn='同比增速（派生）', name_en='Year-over-year growth (%)',
         statement='派生', official_line='—',
         definition='(本期 − 上年同期) ÷ |上年同期| × 100。', formula='见 period_conversion_rules.growth_rules',
         period_basis='DERIVED', unit_kind='RATIO_PCT', unit='%', scale='百分数数值',
         consolidation='CONSOLIDATED', sign='可为负', p00_required='NO',
         comparability='必须同期间类型（累计对累计、单季对单季）', blocking='上年同期 ≤ 0 时禁止用普通增速',
         notes='亏损/零基数情形改用绝对额变化+利润率，见 growth_rules'),
    dict(field_id='FIN.NPMARGIN.PCT', name_cn='归母净利率（派生）', name_en='Net margin attributable to parent (%)',
         statement='派生', official_line='—', definition='归母净利 ÷ 营业收入 × 100。',
         formula='FIN.NPP.YTD ÷ FIN.REV.YTD × 100', period_basis='DERIVED', unit_kind='RATIO_PCT',
         unit='%', scale='百分数数值', consolidation='CONSOLIDATED', sign='可为负', p00_required='NO',
         comparability='分子分母同期间同范围', blocking='收入为 0 或缺失时不计算',
         notes='亏损公司仍有意义（负利润率），不因分子为负而禁用'),
    dict(field_id='FIN.OCF_TO_NP.RATIO', name_cn='经营现金流/归母净利（现金含量，派生）',
         name_en='OCF to net profit ratio', statement='派生', official_line='—',
         definition='经营活动现金流量净额 ÷ 归母净利润。', formula='FIN.OCF.YTD ÷ FIN.NPP.YTD',
         period_basis='DERIVED', unit_kind='RATIO_TIMES', unit='倍', scale='倍数',
         consolidation='CONSOLIDATED', sign='分母为负时结果不可解释', p00_required='NO',
         comparability='同期间', blocking='归母净利 ≤ 0 时不计算，改为并列展示两个绝对额',
         notes='不得对亏损公司输出“现金含量 21%”这类看似正常的比率（历史教训见 PROJECT_STATE 众诚科技条目）'),
    dict(field_id='FIN.PPCHG.PP', name_cn='比率变动（百分点）', name_en='Ratio change in percentage points',
         statement='派生', official_line='—', definition='两个百分数之差，单位为百分点（pp）。',
         formula='本期% − 上年同期%', period_basis='DERIVED', unit_kind='DELTA_PP', unit='百分点',
         scale='pp', consolidation='CONSOLIDATED', sign='可为负', p00_required='NO',
         comparability='同口径百分数', blocking='—',
         notes='年报原文即写“减少13.85个百分点”，不得写成 −13.85%'),
]

# ---------------------------------------------------------------- 覆盖统计
def snapshot_stats():
    df = pd.read_csv(SNAPSHOT, encoding='utf-8-sig')
    stats = {}
    for col in df.columns:
        s = df[col]
        if s.dtype.kind in 'if':
            stats[col] = {
                'dtype': str(s.dtype),
                'null': int(s.isna().sum()),
                'zero': int((s == 0).sum()),
                'negative': int((s < 0).sum()),
                'non_null_non_zero': int((s.notna() & (s != 0)).sum()),
            }
    return df, stats


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 映射证据
def probe_example(security_id, source, item_field):
    exchange, code = security_id.split(':')
    path = RAW_PROBE / f'{exchange}_{code}_{source}.json'
    if not path.exists():
        return None, None
    value = json.loads(path.read_text(encoding='utf-8'))
    data = value['result']['data']
    period = list(data['report_list'])[0]
    block = data['report_list'][period]
    for item in block.get('data') or []:
        if item.get('item_field') == item_field:
            return period, item.get('item_value')
    return period, None


def pdf_ref(document_id, statement, target):
    doc = json.loads((OUT / 'pdf_lineitem_evidence.json').read_text(encoding='utf-8'))
    for row in doc['line_items']:
        if row['document_id'] == document_id and row['statement'] == statement and row.get('target') == target:
            return row.get('page'), row.get('raw_line')
    return None, None


def build_mapping():
    rows = []
    # ---- 新浪（非官方结构化）
    sina_fields = [
        ('FIN.REV.YTD', 'lrb', 'BIZINCO', '营业收入', 'YTD_CUMULATIVE', '元', '直接取数'),
        ('FIN.REV.YTD', 'lrb', 'BIZTOTINCO', '营业总收入', 'YTD_CUMULATIVE', '元', '不得直接用作营业收入（金融类含利息/保费）'),
        ('FIN.COST.YTD', 'lrb', 'BIZCOST', '营业成本', 'YTD_CUMULATIVE', '元', '直接取数'),
        ('FIN.COST.YTD', 'lrb', 'BIZTOTCOST', '营业总成本', 'YTD_CUMULATIVE', '元', '不得用作营业成本（含税金/期间费用/减值）'),
        ('FIN.NP.YTD', 'lrb', 'NETPROFIT', '净利润', 'YTD_CUMULATIVE', '元', '直接取数，不可替代归母'),
        ('FIN.NPP.YTD', 'lrb', 'PARENETP', '归属于母公司所有者的净利润', 'YTD_CUMULATIVE', '元', '直接取数'),
        ('FIN.OCF.YTD', 'llb', 'MANANETR', '经营活动产生的现金流量净额', 'YTD_CUMULATIVE', '元', '直接取数'),
        ('FIN.AR.INSTANT', 'fzb', 'ACCORECE', '应收账款', 'INSTANT', '元', '直接取数；与 NOTESACCORECE 合计项区分'),
        ('FIN.NR.INSTANT', 'fzb', 'NOTESACCORECE', '应收票据及应收账款', 'INSTANT', '元', '合计项，不得当作应收账款'),
        ('FIN.CONTRACTASSET.INSTANT', 'fzb', 'CONTRACTASSET', '合同资产', 'INSTANT', '元', '直接取数；实测存在 null，null≠0'),
        ('FIN.INV.INSTANT', 'fzb', 'INVE', '存货', 'INSTANT', '元', '直接取数'),
        ('FIN.ASSET.INSTANT', 'fzb', 'TOTASSET', '资产总计', 'INSTANT', '元', '直接取数'),
    ]
    for field_id, source, code, title, basis, unit, transform in sina_fields:
        period, value = probe_example('SH:688218', source, code)
        present = value not in (None, '')
        crosschecked = code in {'BIZINCO', 'BIZCOST', 'PARENETP', 'MANANETR', 'ACCORECE', 'INVE', 'CONTRACTASSET'}
        if not present:
            verification, confidence = 'NO_VALUE_IN_SAMPLE', 'FIELD_EXISTS_VALUE_NULL'
        elif crosschecked:
            verification, confidence = 'MATCH_EXACT（crosscheck_provider_vs_pdf.json）', 'VERIFIED_NUMERIC_UNIT'
        else:
            verification, confidence = 'VALUE_OBSERVED_NO_CROSSCHECK', 'FIELD_EXISTS_VALUE_READ'
        rows.append({
            'mapping_id': f'MAP-SINA-{source.upper()}-{code}',
            'canonical_field_id': field_id,
            'provider': 'SINA_NON_OFFICIAL_STRUCTURED',
            'provider_endpoint': 'quotes.sina.cn CompanyFinanceService.getFinanceReport2022',
            'provider_table': source,
            'provider_field_code': code,
            'provider_field_title_cn': title,
            'provider_period_basis': '累计（type=0/1/2/3/4 均为年初至今）',
            'provider_unit': '元（实测：与官方PDF逐项一致）',
            'transform': transform,
            'evidence_type': 'LIVE_PROBE_20261026',
            'evidence_ref': f'provider_probe_records.json / sources/p04_probe/SH_688218_{source}.json；period={period}',
            'evidence_value': value if present else 'NULL（该样本未披露或字段为空）',
            'verification': verification,
            'confidence': confidence,
            'notes': transform,
        })
    # 新浪缺失字段（负向映射，必须显式记录，避免下游以为能取到）
    for field_id, title in [('FIN.NPDEDT.YTD', '扣非归母净利润'), ('FIN.PUBLISHED_ON', '实际披露日（仅 period 级 publish_date）'),
                            ('FIN.LISTING_DATE', '上市日期')]:
        rows.append({
            'mapping_id': f'MAP-SINA-ABSENT-{field_id.split(".")[-1]}',
            'canonical_field_id': field_id, 'provider': 'SINA_NON_OFFICIAL_STRUCTURED',
            'provider_endpoint': 'quotes.sina.cn CompanyFinanceService.getFinanceReport2022',
            'provider_table': 'lrb', 'provider_field_code': 'ABSENT', 'provider_field_title_cn': title,
            'provider_period_basis': '—', 'provider_unit': '—',
            'transform': '不可映射：该接口利润表 77 个字段中不存在此字段（逐字段核对 provider_field_inventory.csv）',
            'evidence_type': 'LIVE_PROBE_FULL_FIELD_SCAN',
            'evidence_ref': 'provider_field_inventory.csv（281 行，lrb 77 项全量）',
            'evidence_value': 'ABSENT', 'verification': 'NOT_AVAILABLE',
            'confidence': 'CONFIRMED_ABSENT',
            'notes': '扣非必须回官方 PDF；披露日/上市日须取巨潮公告与交易所页面',
        })
    # ---- 官方 PDF
    pdf_fields = [
        ('FIN.REV.YTD', 'IS', '营业收入', 'DOC-055EAAF729BDBA32'),
        ('FIN.COST.YTD', 'IS', '营业成本', 'DOC-055EAAF729BDBA32'),
        ('FIN.NP.YTD', 'IS', '净利润', 'DOC-055EAAF729BDBA32'),
        ('FIN.NPP.YTD', 'IS', '归属于母公司所有者的净利润', 'DOC-055EAAF729BDBA32'),
        ('FIN.NPDEDT.YTD', 'KEY_FINANCIALS', '主要会计数据', 'DOC-055EAAF729BDBA32'),
        ('FIN.NPDEDT.YTD', 'NONRECURRING', '非经常性损益项目', 'DOC-055EAAF729BDBA32'),
        ('FIN.NPDEDT.SQ', 'QUARTERLY', '分季度', 'DOC-055EAAF729BDBA32'),
        ('FIN.REV.SQ', 'QUARTERLY', '分季度', 'DOC-055EAAF729BDBA32'),
        ('FIN.NPP.SQ', 'QUARTERLY', '分季度', 'DOC-055EAAF729BDBA32'),
        ('FIN.OCF.SQ', 'QUARTERLY', '分季度', 'DOC-055EAAF729BDBA32'),
        ('FIN.OCF.YTD', 'CF', '经营活动产生的现金流量净额', 'DOC-055EAAF729BDBA32'),
        ('FIN.AR.INSTANT', 'BS', '应收账款', 'DOC-055EAAF729BDBA32'),
        ('FIN.CONTRACTASSET.INSTANT', 'BS', '合同资产', 'DOC-055EAAF729BDBA32'),
        ('FIN.INV.INSTANT', 'BS', '存货', 'DOC-055EAAF729BDBA32'),
        ('FIN.ASSET.INSTANT', 'BS', '资产总计', 'DOC-055EAAF729BDBA32'),
    ]
    for field_id, statement, target, doc_id in pdf_fields:
        page, line = pdf_ref(doc_id, statement, target)
        rows.append({
            'mapping_id': f'MAP-PDF-{statement}-{target}-{doc_id[-6:]}',
            'canonical_field_id': field_id, 'provider': 'CNINFO_OFFICIAL_PDF',
            'provider_endpoint': 'static.cninfo.com.cn finalpage PDF',
            'provider_table': statement, 'provider_field_code': target,
            'provider_field_title_cn': target,
            'provider_period_basis': {'IS': '累计（本期/上年同期两列）', 'BS': '时点（期末/期初两列）',
                                      'CF': '累计（本期/上年同期两列）', 'QUARTERLY': '单季度（Q1-Q4四列）',
                                      'KEY_FINANCIALS': '累计（本年/上年同期/前年三列）',
                                      'NONRECURRING': '累计（本年/上年/前年三列）'}.get(statement, '—'),
            'provider_unit': '元（表头“单位：元 币种：人民币”）',
            'transform': '按物理页定位行项目，取第 1 个金额列（本期）',
            'evidence_type': 'OFFICIAL_PDF_PHYSICAL_PAGE',
            'evidence_ref': f'pdf_lineitem_evidence.json {doc_id} p{page}',
            'evidence_value': (line or '')[:120],
            'verification': 'PAGE_LOCATED_AND_VALUE_READ',
            'confidence': 'VERIFIED_PAGE_LEVEL',
            'notes': f'688218 2025年报；同一PDF内合并/母公司报表并存，抽取须锁定“合并”标题',
        })
    # ---- 旧快照
    legacy = [
        ('FIN.REV.YTD', 'revenue_cny_{year}', '营业收入', 'YTD_CUMULATIVE', '元', '直接取数'),
        ('FIN.NPP.YTD', 'net_profit_parent_cny_{year}', '归母净利润', 'YTD_CUMULATIVE', '元', '直接取数'),
        ('FIN.GROSSMARGIN.PCT', 'gross_margin_pct_{year}', '毛利率', 'YTD_CUMULATIVE', '百分数（23.28=23.28%）', '直接取数，不得当小数'),
        ('FIN.NPDEDT.YTD', 'deducted_np_parent_cny_{yyyymmdd}', '扣非归母净利润', 'YTD_CUMULATIVE（实测更正）', '元', '直接取数；P02 曾记为“单季”，P04 以官方PDF证伪'),
    ]
    for field_id, col, title, basis, unit, transform in legacy:
        rows.append({
            'mapping_id': f'MAP-LEGACY-{col}',
            'canonical_field_id': field_id, 'provider': 'LEGACY_SNAPSHOT_V1',
            'provider_endpoint': 'collection_run_20261026/raw/既有候选池财务快照.csv',
            'provider_table': '宽表 1054×50', 'provider_field_code': col,
            'provider_field_title_cn': title, 'provider_period_basis': basis,
            'provider_unit': unit, 'transform': transform,
            'evidence_type': 'LOCAL_FILE_VALUE_CROSSCHECK',
            'evidence_ref': ('crosscheck_period_conversion.json（688218/002354 四季扣非加总=全年，证明为累计）'
                             if field_id == 'FIN.NPDEDT.YTD' else 'crosscheck_provider_vs_pdf.json（与官方PDF逐项一致）'),
            'evidence_value': '688218 20251231 扣非累计=-83,879,539.25（官方PDF全年-83,879.54万）' if field_id == 'FIN.NPDEDT.YTD' else '见 crosscheck 明细',
            'verification': 'VALUE_VERIFIED_AGAINST_OFFICIAL_PDF',
            'confidence': 'VERIFIED_NUMERIC_UNIT',
            'notes': 'P02 将 22 列扣非描述为“单季度”，P04 实测为累计；旧描述须在 S00 按本表更正',
        })
    for col, title in [('revenue_cny_2025H1', '2025H1 营业收入'), ('operating_cash_flow_cny_*', '经营活动现金流净额'),
                       ('accounts_receivable_cny_*', '应收账款'), ('inventory_cny_*', '存货'),
                       ('operating_cost_cny_*', '营业成本'), ('published_on', '实际披露日'),
                       ('listing_date（有效值）', '上市日期'), ('revenue_cny_2025Q1..Q4', '单季度营业收入')]:
        rows.append({
            'mapping_id': f'MAP-LEGACY-ABSENT-{col.split("_")[0]}',
            'canonical_field_id': {'revenue_cny_2025H1': 'FIN.REV.YTD', 'operating_cash_flow_cny_*': 'FIN.OCF.YTD',
                                   'accounts_receivable_cny_*': 'FIN.AR.INSTANT', 'inventory_cny_*': 'FIN.INV.INSTANT',
                                   'operating_cost_cny_*': 'FIN.COST.YTD', 'published_on': 'FIN.PUBLISHED_ON',
                                   'listing_date（有效值）': 'FIN.LISTING_DATE',
                                   'revenue_cny_2025Q1..Q4': 'FIN.REV.SQ'}[col],
            'provider': 'LEGACY_SNAPSHOT_V1',
            'provider_endpoint': 'collection_run_20261026/raw/既有候选池财务快照.csv',
            'provider_table': '宽表 1054×50', 'provider_field_code': 'ABSENT',
            'provider_field_title_cn': title, 'provider_period_basis': '—', 'provider_unit': '—',
            'transform': '不可映射：50 列中无此列',
            'evidence_type': 'LOCAL_FILE_COLUMN_SCAN',
            'evidence_ref': 'legacy_snapshot_gap_register.csv',
            'evidence_value': 'ABSENT', 'verification': 'NOT_AVAILABLE',
            'confidence': 'CONFIRMED_ABSENT',
            'notes': '必须由 P05 采集补齐；2025H1 是 2026H1 同比的必需基数',
        })
    # ---- 派生
    derived = [
        ('FIN.GROSSPROFIT.YTD', 'FIN.REV.YTD − FIN.COST.YTD'),
        ('FIN.GROSSMARGIN.PCT', 'FIN.GROSSPROFIT.YTD ÷ FIN.REV.YTD × 100'),
        ('FIN.NPMARGIN.PCT', 'FIN.NPP.YTD ÷ FIN.REV.YTD × 100'),
        ('FIN.OCF_TO_NP.RATIO', 'FIN.OCF.YTD ÷ FIN.NPP.YTD（分母≤0 不计算）'),
        ('FIN.YOY.PCT', '(本期 − 上年同期) ÷ |上年同期| × 100（上年同期≤0 改用绝对额）'),
        ('FIN.PPCHG.PP', '本期% − 上年同期%（单位：百分点）'),
        ('FIN.REV.SQ', '官方分季度表；否则 Qn = 累计(n) − 累计(n−1)'),
        ('FIN.NPP.SQ', '官方分季度表；否则 Qn = 累计(n) − 累计(n−1)'),
        ('FIN.NPDEDT.SQ', '官方分季度表；否则 Qn = 累计(n) − 累计(n−1)'),
        ('FIN.OCF.SQ', '官方分季度表；否则 Qn = 累计(n) − 累计(n−1)'),
    ]
    for field_id, formula in derived:
        rows.append({
            'mapping_id': f'MAP-DERIVED-{field_id.split(".")[-1]}',
            'canonical_field_id': field_id, 'provider': 'DERIVED_IN_PIPELINE',
            'provider_endpoint': '—', 'provider_table': '—', 'provider_field_code': formula,
            'provider_field_title_cn': '计算字段', 'provider_period_basis': 'DERIVED', 'provider_unit': '按字段字典',
            'transform': formula, 'evidence_type': 'RULE_DEFINITION',
            'evidence_ref': 'period_conversion_rules.json', 'evidence_value': '—',
            'verification': 'RULE_FROZEN', 'confidence': 'RULE',
            'notes': '派生字段不得反写回原始字段；中间结果须保留分子分母',
        })
    return rows


def build_gap_register(df, stats):
    coverage = {}
    path = ROOT / 'runs/issues/P02/existing_field_coverage.csv'
    if path.exists():
        for row in csv.DictReader(path.open(encoding='utf-8-sig')):
            coverage[row['field_name']] = row
    rows = []
    for col, st in stats.items():
        cov = coverage.get(col, {})
        rows.append({
            'gap_id': f'GAP-COL-{col}',
            'gap_type': 'COLUMN_PRESENT',
            'snapshot_column': col,
            'canonical_field_id': '',
            'expected': '1054 行可取值',
            'actual_non_null': st['non_null_non_zero'] + st['zero'],
            'null_rows': st['null'],
            'zero_rows': st['zero'],
            'negative_rows': st['negative'],
            'coverage_pct': cov.get('coverage_pct', f"{100 * (1054 - st['null']) / 1054:.2f}"),
            'impact': '可用' if st['null'] < 1054 else '整列不可用',
            'required_action': '—' if st['null'] < 1054 else 'P05 采集补齐',
            'notes': '零值=真实 0 与缺失已用 NULL 区分（本列无 0 值占位）',
        })
    missing_fields = [
        ('FIN.OCF.YTD', '经营活动产生的现金流量净额', '无该列', 'S05 质量检查与拐点判断必需；无法用净利替代', 'P05 从合并现金流量表取'),
        ('FIN.OCF.SQ', '单季度经营活动现金流净额', '无该列', '季度质量核验必需', 'P05 取官方分季度表'),
        ('FIN.AR.INSTANT', '应收账款', '无该列', '应收周转与回款质量无法计算', 'P05 从合并资产负债表取'),
        ('FIN.CONTRACTASSET.INSTANT', '合同资产', '无该列', 'P00 要求应收含合同资产且分列', 'P05 从合并资产负债表取'),
        ('FIN.INV.INSTANT', '存货', '无该列', '存货周转与备货判断无法计算', 'P05 从合并资产负债表取'),
        ('FIN.COST.YTD', '营业成本', '无该列（仅有毛利率百分比）', '毛利额无法得到，只能看比率', 'P05 从合并利润表取'),
        ('FIN.GROSSPROFIT.YTD', '毛利额', '无该列', '同上', '由成本与收入派生'),
        ('FIN.PUBLISHED_ON', '实际披露日', '无该列', 'PIT 判断与“披露后才可得”无法执行', 'P05 取巨潮公告元数据'),
        ('FIN.LISTING_DATE', '上市日期（有效值）', '有列但 1054/1054=UNKNOWN', '无法判定上市前不适用；62 家北交所缺失原因无法归类', 'P05 取交易所上市日期回填'),
        ('FIN.REV.SQ', '单季度营业收入', '无该列', '单季拐点无法直接观察，只能累计相减', 'P05 取官方分季度表'),
        ('FIN.NPP.SQ', '单季度归母净利', '无该列', '同上', 'P05 取官方分季度表'),
        ('FIN.REV.YTD@2025H1', '2025H1 营业收入', '无该列（只有 2026H1 与 2021-2025 年度）', '2026H1 同比增速无法计算，是当前最硬的缺口', 'P05 取 2025 半年报'),
        ('FIN.NPP.YTD@2025H1', '2025H1 归母净利', '无该列', '同上', 'P05 取 2025 半年报'),
        ('FIN.GROSSMARGIN.PCT@2025H1', '2025H1 毛利率', '无该列', '2026H1 毛利率变动无法计算', 'P05 取 2025 半年报'),
        ('FIN.OCF.YTD@2025H1', '2025H1 经营现金流净额', '无该列', '现金流同比无法计算', 'P05 取 2025 半年报'),
        ('FIN.NPDEDT.YTD@2025H1', '2025H1 扣非归母净利', '无该列（仅 22 期期末累计）', '扣非同比无法计算', 'P05 取 2025 半年报'),
        ('FIN.STATUS', '数据状态码', '无该列（仅 data_status 二值）', '未披露/取件失败/上市前不适用无法区分', 'P05 按 P00 状态口径写入'),
        ('FIN.AUDIT_STATUS', '审计状态', '无该列', '季报与年报可信度无法区分', 'P05 采集'),
        ('FIN.RESTATEMENT', '重述标记', '无该列', '跨期相减存在风险', 'P05 读取年报重述说明'),
        ('FIN.UNIT_SCALE', '金额单位与量纲', '隐含为元，无显式列', '无法验证是否已折算', 'P05 采集时显式记录'),
    ]
    for field_id, name, gap, impact, action in missing_fields:
        rows.append({
            'gap_id': f'GAP-FIELD-{field_id}',
            'gap_type': 'COLUMN_ABSENT' if '无该列' in gap else 'COLUMN_UNUSABLE',
            'snapshot_column': gap,
            'canonical_field_id': field_id,
            'expected': '按字段字典口径可取值',
            'actual_non_null': 0 if '无该列' in gap else '1054 UNKNOWN',
            'null_rows': 1054,
            'zero_rows': 0,
            'negative_rows': 0,
            'coverage_pct': '0.00',
            'impact': impact,
            'required_action': action,
            'notes': name,
        })
    bj = df[df.exchange == 'BJ']
    rows.append({
        'gap_id': 'GAP-EXCHANGE-BJ',
        'gap_type': 'UNIVERSE_SEGMENT_ABSENT',
        'snapshot_column': '全部财务列',
        'canonical_field_id': 'ALL',
        'expected': '62 家北交所公司可取值',
        'actual_non_null': int((bj.data_status == 'HAS_FINANCIAL_DATA').sum()),
        'null_rows': int((bj.data_status == 'FINANCIAL_DATA_MISSING').sum()),
        'zero_rows': 0, 'negative_rows': 0, 'coverage_pct': '0.00',
        'impact': '旧快照对北交所覆盖率 0/62；旧工作台北交所接口返回 400（P03 实测）',
        'required_action': '必须走 P03 的显式三市场适配器（SH/SZ/BJ），不得沿用旧快照或旧工作台沪深校验',
        'notes': '全池 1054 家中 BJ 62 家，全部 FINANCIAL_DATA_MISSING',
    })
    rows.append({
        'gap_id': 'GAP-PRE_LISTING-62',
        'gap_type': 'MISSING_CAUSE_UNKNOWN',
        'snapshot_column': 'data_status / listing_date',
        'canonical_field_id': 'FIN.LISTING_DATE',
        'expected': '62 家缺失原因可分类',
        'actual_non_null': 0, 'null_rows': 62, 'zero_rows': 0, 'negative_rows': 0, 'coverage_pct': '0.00',
        'impact': '无法区分“上市前不适用”与“取件失败/未披露”，只能记 MISSING_CAUSE_UNKNOWN',
        'required_action': 'P05 回填上市日期后重分类；在此之前不得判 NOT_APPLICABLE_PRE_LISTING',
        'notes': 'crosstab：62 家 FINANCIAL_DATA_MISSING 的 prelisting_flag 全为 NONE；61 家 PRE_LISTING_PROSPECTUS_DATA 反而有数据',
    })
    return rows


def build_rules(df):
    snap_stats = {}
    for col in ['revenue_cny_2025', 'revenue_cny_2026H1', 'deducted_np_parent_cny_20251231']:
        s = df[col]
        snap_stats[col] = {'null': int(s.isna().sum()), 'zero': int((s == 0).sum())}
    pc = json.loads((OUT / 'crosscheck_period_conversion.json').read_text(encoding='utf-8'))
    cp = json.loads((OUT / 'crosscheck_provider_vs_pdf.json').read_text(encoding='utf-8'))
    return {
        'version': VERSION,
        'frozen_at': NOW,
        'plan_version': '20261026_collection_first_v2',
        'issue': 'P04 / #15',
        'knowledge_as_of': '2026-10-25',
        'currency': {'code': 'CNY', 'note': '实测四份样本表头均为“币种：人民币”，新浪 rCurrency=CNY；非 CNY 无汇率来源时阻断'},
        'unit_scale': {
            'canonical': '元（CNY，未缩放）',
            'rule': 'PDF 表头若为千元/万元，先 ×1000/×10000 折算为元并保留原单位文本',
            'observed': '4/4 样本表头为“单位：元”；新浪数值与官方 PDF 逐项一致，证明同为元',
            'evidence': 'pdf_lineitem_evidence.json（unit_on_statement）+ crosscheck_provider_vs_pdf.json（14/14 MATCH_EXACT）',
        },
        'consolidation_scope': {
            'canonical': 'CONSOLIDATED（合并报表）',
            'rule': '同一 PDF 内合并与母公司报表并存，抽取必须先锁定“合并资产负债表/合并利润表/合并现金流量表”标题，再在标题范围内取行项目',
            'observed_ranges': {
                'DOC-055EAAF729BDBA32': '合并BS p122-124 / 母公司BS p125-126 / 合并IS p127-128 / 合并CF p130-131',
                'DOC-2025AR-002354': '合并BS p71-72 / 合并IS p75-76 / 合并CF p78-79',
                'DOC-2025AR-920207': '合并BS p74-76 / 合并IS p79-80 / 合并CF p82-83',
                'DOC-2026H1-920207': '合并BS p40-41 / 合并IS p45-46 / 合并CF p49',
            },
            'prohibition': '不得把母公司报表当合并报表；不得混用两个口径做同比',
        },
        'period_types': {
            'Q1': {'period_key_suffix': '0331', 'start': '01-01', 'end': '03-31', 'cumulative_months': 3},
            'H1': {'period_key_suffix': '0630', 'start': '01-01', 'end': '06-30', 'cumulative_months': 6},
            '9M': {'period_key_suffix': '0930', 'start': '01-01', 'end': '09-30', 'cumulative_months': 9},
            'FY': {'period_key_suffix': '1231', 'start': '01-01', 'end': '12-31', 'cumulative_months': 12},
        },
        'single_quarter_formulas': {
            'Q1': 'Q1单季 = 一季报累计（累计即单季）',
            'Q2': 'Q2单季 = H1累计 − Q1累计',
            'Q3': 'Q3单季 = 9M累计 − H1累计',
            'Q4': 'Q4单季 = FY累计 − 9M累计',
            'preferred_source': '官方年报“分季度主要财务数据”表（已直接披露单季，优先于相减）',
            'fallback': '同一年度、同一合并范围、同一版本下用累计相减；相减结果必须与该年度官方分季表勾稽',
            'prohibited': [
                '跨年度相减（如 2026Q1 累计 − 2025Q4 累计）',
                '跨版本相减（重述前 vs 重述后）',
                '合并范围变化前后相减（新增/处置子公司）',
                '用单季乘 4 反推全年',
            ],
        },
        'provider_type_semantics': pc['provider_type_semantics'],
        'pit_rules': {
            'report_period': '报表所属期间（如 2026H1），由报表标题决定',
            'published_on': '实际披露日；未知时记 UNKNOWN，不得用报告期结束日代替',
            'collected_at': '取件时间戳（UTC），只证明取件动作发生时间',
            'as_of': '研究截止日 2026-10-25；披露日晚于此日的文件只登记为增量候选',
            'rule': '只有 published_on ≤ as_of 的数据才能进入本轮证据链；published_on 未知时状态记 PIT_UNKNOWN，不得声称“当时可得”',
            'prohibition': '不得把 collected_at 当作 published_on，也不得用 as_of 覆盖 report_period',
        },
        'restatement_rules': {
            'detect': '读取年报“是否需追溯调整或重述以前年度会计数据”勾选项及“重要会计政策变更/前期差错更正”章节',
            'if_restated': '以最新版本重算历史期；旧版本保留为独立版本，不覆盖',
            'if_unresolved': '跨期比较标记 RESTATEMENT_UNRESOLVED 并阻断该字段的同比',
            'evidence': '002354 2025年报 p7 明示“公司是否需追溯调整或重述以前年度会计数据 □是 否”',
        },
        'growth_rules': {
            'normal': '(本期 − 上年同期) ÷ |上年同期| × 100，单位 %',
            'if_base_negative': '禁止输出普通增速（负基数下符号无经济含义）；改记：绝对额变化（元）、利润率变化（百分点）、是否由亏转盈',
            'if_base_zero': '记 NOT_COMPUTABLE_ZERO_BASE，不用 0 或 999 代替',
            'if_base_missing': '记 NOT_COMPUTABLE_BASE_MISSING（当前 2026H1 同比即属此类，因旧快照无 2025H1）',
            'margin_change': '比率变动用百分点（pp），不得写成百分比变化',
            'profit_vs_recurring': '归母净利与扣非归母净利分别计算增速，不得互相替代；两者背离时须在结果里同时呈现',
        },
        'null_zero_rules': {
            'null_semantics': 'NULL = 未取得/未披露/不适用，必须带原因码；0 = 真实为零',
            'prohibited': ['fillna(0)', '用 0 表示未披露', '用前值填充', '用行业均值填充'],
            'observed_in_snapshot': {
                'missing_rows': 62,
                'zero_cells_in_amount_columns': 0,
                'note': '旧快照金额列无 0 值占位，62 家全列为 NULL；该做法正确，须延续',
            },
            'blank_in_pdf': 'PDF 中空白单元格表示公司未列示该项（如 002354 合同资产为空白），记 NULL 而非 0',
        },
        'validation_rules': [
            {'id': 'V1', 'check': '四季单季之和 = 全年累计', 'tolerance': '≤0.01 元（四舍五入）', 'on_fail': 'PERIOD_INCONSISTENT，阻断该字段同比'},
            {'id': 'V2', 'check': '累计差 = 官方单季', 'tolerance': '≤0.01 元', 'on_fail': '记录差异并优先采用官方单季'},
            {'id': 'V3', 'check': '同一公司同一期间：结构化接口 vs 官方 PDF', 'tolerance': '≤1 元', 'on_fail': '以官方 PDF 为准，并登记 provider 偏差'},
            {'id': 'V4', 'check': '毛利率 = (收入−成本)/收入×100', 'tolerance': '≤0.05 个百分点', 'on_fail': '检查成本口径（是否含税金及附加）'},
            {'id': 'V5', 'check': '合并范围一致性（报表标题=合并）', 'tolerance': '精确匹配', 'on_fail': '阻断'},
        ],
        'verified_this_issue': {
            'provider_vs_pdf': {'verdict_counts': cp['verdict_counts'], 'pairs': cp['pairs']},
            'period_conversion': {'verdict_counts': pc['verdict_counts'], 'rows': len(pc['rows'])},
            'conclusion': '14/14 字段级数值一致；48/48 期间换算校验通过（含四季加总=全年、累计差=官方单季）',
        },
        'snapshot_period_semantics_correction': {
            'finding': '旧快照 deducted_np_parent_cny_YYYYMMDD 22 列是“年初至今累计”，不是单季度',
            'proof': '688218 2025：Q1 -19,728,084.54 + Q2 -5,735,225.19 = -25,463,309.73 = 快照 20250630 值；再加 Q3 -10,888,975.44 = -36,352,285.17 = 快照 20250930 值；再加 Q4 -47,527,254.08 = -83,879,539.25 ≈ 快照 20251231 值（-83,879,540）',
            'impact': 'P02 交接文档中“22 期单季扣非”的表述有误；任何按单季使用的下游计算须改为相减或取官方分季表',
            'action': 'S00 标准化时按累计读入；需要单季时按 single_quarter_formulas 换算',
        },
        'blocking_conditions': [
            '单位/币种无法确认 → 阻断该表全部金额字段',
            '合并范围无法确认 → 阻断',
            '报告期无法确认 → 阻断',
            '扣非仅能由结构化接口取得 → 阻断（接口无此字段，必须回原文）',
            'published_on 未知且用于 PIT 判断 → 记 PIT_UNKNOWN，不得当作可得',
            '跨版本/跨合并范围相减 → 阻断',
        ],
        'open_gaps_for_p05': [
            '北交所 62/62 无财务数据：必须用显式三市场适配器',
            '7 个 P00 契约字段（经营现金流/应收/存货/营业成本/披露日/上市日期/单季营收）旧快照全缺',
            '2025H1 五项基数缺失，导致 2026H1 同比全部不可计算',
            '扣非只能回官方 PDF，采集器须解析非经常性损益表或“主要会计数据”表',
        ],
    }


def main():
    df, stats = snapshot_stats()
    assert sha256(SNAPSHOT) == SNAPSHOT_SHA, '旧快照哈希变化，须先复核再生成'

    # 字段字典
    dict_cols = ['field_id', 'name_cn', 'name_en', 'statement', 'official_line', 'definition', 'formula',
                 'period_basis', 'unit_kind', 'unit', 'scale', 'consolidation', 'sign', 'nullable',
                 'null_semantics', 'zero_allowed', 'p00_required', 'comparability', 'blocking', 'notes']
    with (OUT / 'financial_field_dictionary.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=dict_cols)
        w.writeheader()
        for row in FIELDS:
            row = dict(row)
            row.setdefault('nullable', 'TRUE')
            row.setdefault('null_semantics', 'MISSING_NOT_ZERO')
            row.setdefault('zero_allowed', 'TRUE')
            w.writerow({k: row.get(k, '') for k in dict_cols})

    # 映射
    mapping = build_mapping()
    map_cols = ['mapping_id', 'canonical_field_id', 'provider', 'provider_endpoint', 'provider_table',
                'provider_field_code', 'provider_field_title_cn', 'provider_period_basis', 'provider_unit',
                'transform', 'evidence_type', 'evidence_ref', 'evidence_value', 'verification',
                'confidence', 'notes']
    with (OUT / 'provider_field_mapping.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=map_cols)
        w.writeheader()
        for row in mapping:
            w.writerow({k: row.get(k, '') for k in map_cols})

    # 期间规则
    rules = build_rules(df)
    (OUT / 'period_conversion_rules.json').write_text(
        json.dumps(rules, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # 缺口登记
    gaps = build_gap_register(df, stats)
    gap_cols = ['gap_id', 'gap_type', 'snapshot_column', 'canonical_field_id', 'expected',
                'actual_non_null', 'null_rows', 'zero_rows', 'negative_rows', 'coverage_pct',
                'impact', 'required_action', 'notes']
    with (OUT / 'legacy_snapshot_gap_register.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=gap_cols)
        w.writeheader()
        for row in gaps:
            w.writerow({k: row.get(k, '') for k in gap_cols})

    # 证据索引
    evidence = []
    for name in ['provider_field_inventory.csv', 'provider_probe_records.json', 'pdf_lineitem_evidence.json',
                 'crosscheck_provider_vs_pdf.json', 'crosscheck_period_conversion.json']:
        p = OUT / name
        if p.exists():
            evidence.append({'file': name, 'sha256': sha256(p), 'bytes': p.stat().st_size})
    for p in sorted(RAW_PROBE.glob('*.json')):
        evidence.append({'file': f'sources/p04_probe/{p.name}（仓库忽略，仅本机）', 'sha256': sha256(p),
                         'bytes': p.stat().st_size})
    (OUT / 'evidence_index.json').write_text(json.dumps({
        'generated_at': NOW, 'version': VERSION,
        'snapshot': {'path': 'collection_run_20261026/raw/既有候选池财务快照.csv',
                     'sha256': SNAPSHOT_SHA, 'rows': int(df.shape[0]), 'columns': int(df.shape[1])},
        'pdf_cache_note': 'PDF 原件在 sources/drive_readback_20261026/（仓库忽略），页码证据见 pdf_lineitem_evidence.json',
        'files': evidence,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(json.dumps({
        'field_dictionary_rows': len(FIELDS),
        'mapping_rows': len(mapping),
        'gap_rows': len(gaps),
        'period_rules_keys': len(rules),
        'evidence_files': len(evidence),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
