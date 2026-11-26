#!/usr/bin/env python3
"""Deterministic builder for #45 R01 (#59 R01_BATCH_01 + #60 R01_BATCH_02, 10 TIER_1 companies)."""

import csv
import hashlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
R01_DIR = ROOT / "runs" / "issues" / "R01"
FIXED_NOW = os.environ.get("R01_FIXED_NOW", "2026-11-26T22:50:00+08:00")
KNOWLEDGE_AS_OF = "2026-10-25"

INPUT_PATHS = [
    "runs/issues/R01/release_20261126.json",
    "runs/issues/R00/acceptance_r00_batch01_02_20261126.json",
    "runs/issues/R00/business_batch_dispatch.csv",
    "runs/issues/R00/business_review_register.csv",
    "runs/issues/R00/batch01_evidence_quotes.csv",
    "runs/issues/R00/batch02_evidence_quotes.csv",
    "runs/issues/R00/inputs_batch01/ai1_300607_002747_business_review.yaml",
    "runs/issues/R00/inputs_batch01/ai2_002472_002979_business_review.yaml",
    "runs/issues/R00/inputs_batch01/codebuddy_920593_draft.json",
    "runs/issues/R00/inputs_batch02/batch02_5companies_business_review.yaml",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
    "runs/issues/S05/quality_flags.csv",
    "runs/issues/S05/quality_decision_log.csv",
    "runs/issues/S08/business_verification_candidates.csv",
    "data/methodology_decision_20261107.json",
]

FORBIDDEN_PHRASES = [
    "贡献约4.40亿元收入",
    "收入下限",
    "可佐证的下限",
    "只能作下限参考",
    "参股灵博12%",
    "均为参股不并表",
    "思哲睿/灵博（权益法）",
]

# Structured attribution & revenue scope facts strictly traced to R00 accepted evidence (knowledge_as_of=2026-10-25).
COMPANY_ATTRIBUTION = {
    "SZ:300607": {
        "revenue_scope_tier": "MIXED_SEGMENT_DISCLOSED",
        "fy2025_total_rev_cny": "2510080513.47",
        "fy2025_mixed_or_disclosed_line_name": "工业机器人及自动化应用系统（含本体与自动化解决方案）",
        "fy2025_mixed_or_disclosed_rev_cny": "685138644.55",
        "fy2025_mixed_share_pct": "27.30",
        "fy2025_pure_robot_rev_cny": "300432856.32",
        "anchor_total_rev_cny": "1288243896.10",
        "anchor_mixed_or_disclosed_line_name": "工业机器人及自动化应用系统（H1未拆分本体与集成）",
        "anchor_mixed_or_disclosed_rev_cny": "707279751.48",
        "anchor_mixed_share_pct": "54.90",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "母公司及江苏拓斯达机器人、矩阵智拓(51%)并表；矩阵智拓2025年净亏343.11万元且未单列收入",
        "revenue_scope_limit": "FY2025单列机器人本体300,432,856.32元(自制284.58M+贸易15.86M)；2026H1 707.28M为本体与自动化应用系统合并口径，纯本体金额未拆分；注塑装备/数控机床/智能能源不计入机器人收入",
        "revenue_attribution": "2026H1工业机器人及自动化应用系统707.28M(+121.62%)拉动收入结构大幅转向机器人及自动化，同时收缩低毛利智能能源业务；但公司明确增长主要由自动化应用系统与3C客户合作驱动，非纯本体放量",
        "margin_attribution": "合并毛利率同比改善(M04=+1.68pp)，得益于低毛利智能能源收缩；但工业机器人及自动化应用系统板块自身毛利率同比下降10.46pp至30.75%，反映集成项目占比提高",
        "recurring_profit_attribution": "2026H1利润改善由主营规模增长、低毛利能源业务收缩及应收回款改善带来信用减值减少共同驱动，无RH06低基数/非经常性预警",
        "cash_flow_attribution": "2026H1经营现金流净额146.92M，经营现金流/归母净利M08=1.4087(正常，RH04未触发)，回款与利润匹配度良好",
        "contract_liabilities": "项目制模式下合同资产占比同比显著下降(M12=-23.94pp)，RH02按项目制豁免；合同负债变化需结合自动化系统交付验收节奏跟踪",
        "backlog_orders": "2026H1披露工业机器人签单约6,800台、出货约5,500台（工业机器人整体台数口径，非人形机器人小拓订单，不可折算金额）；人形小拓仅处客户场景小批量验证",
        "cip_robot_capacity": "UNKNOWN（本轮R00已核页未单列在建工程机器人产能明细，留R03专项核查）",
        "attribution_verdict": "CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE",
        "r03_priority_bucket": "R03_PRIORITY_A",
        "r03_watch_points": "跟踪机器人本体与自动化系统拆分毛利率走势、自产多关节占比及人形小拓能否由验证转为正式订单",
    },
    "SZ:002472": {
        "revenue_scope_tier": "UNDISCLOSED_IN_BROADER_LINE",
        "fy2025_total_rev_cny": "9112171720.39",
        "fy2025_mixed_or_disclosed_line_name": "减速器及其他（含机器人RV减速器及非机器人传动产品）",
        "fy2025_mixed_or_disclosed_rev_cny": "795052336.68",
        "fy2025_mixed_share_pct": "8.73",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "4558950064.86",
        "anchor_mixed_or_disclosed_line_name": "减速器及其他（混合科目，不能等同于RV减速器单独收入）",
        "anchor_mixed_or_disclosed_rev_cny": "440341985.30",
        "anchor_mixed_share_pct": "9.67",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "环动科技持股61.29%并表（母公司年报/半年报未单列环动单体营收与利润）；科创板分拆尚在进行中",
        "revenue_scope_limit": "机器人RV减速器未单列，并入“减速器及其他”混合科目（2026H1 440.34M，+26.18%）；智能执行机构（扫地机/eBike/汽车）与汽车齿轮均非工业机器人业务",
        "revenue_attribution": "2026H1总营收4,558.95M(+7.80%)，“减速器及其他”440.34M(+26.18%，占比9.67%)增速显著快于整体，但占总盘不足一成且含非机器人减速器，不能将公司整体增长全归机器人",
        "margin_attribution": "合并毛利率微降(M04=-0.29pp，RH05未触发)；“减速器及其他”自算毛利率由FY2025的38.47%升至2026H1的47.47%，但因含非机器人项且环动单体未披露，纯RV盈利能力留待核",
        "recurring_profit_attribution": "主业盈利稳健，无RH06触发；但环动科技单体净利润未披露，机器人板块对合并扣非净利的实际贡献比例UNKNOWN",
        "cash_flow_attribution": "2026H1经营现金流净额1,111.59M(+13.38%)，M08=1.8948(优异，RH04未触发)，整体造血能力强",
        "contract_liabilities": "合同资产连续两期报表空白(REPORTED_BLANK，RH02待核)；存货2,413.44M(+8.43%)，周转天数由117.3天微升至125.8天，幅度温和",
        "backlog_orders": "UNKNOWN（2025年报与2026半年报未披露机器人减速器在手订单金额或台数，不填0）",
        "cip_robot_capacity": "UNKNOWN（环动科技分拆募投及在建工程产能对应需待分拆招股/问询回复核查）",
        "attribution_verdict": "MIXED_OR_UNQUANTIFIED_DRIVER",
        "r03_priority_bucket": "R03_PRIORITY_A",
        "r03_watch_points": "跟踪环动科技科创板分拆进展及单体营收/毛利披露，核实RV减速器在“减速器及其他”中的真实占比与谐波自产情况",
    },
    "SZ:002979": {
        "revenue_scope_tier": "UNDISCLOSED_IN_BROADER_LINE",
        "fy2025_total_rev_cny": "1873838550.29",
        "fy2025_mixed_or_disclosed_line_name": "伺服系统类（通用工控为主，推断含未单列的机器人核心部件）",
        "fy2025_mixed_or_disclosed_rev_cny": "921586745.82",
        "fy2025_mixed_share_pct": "49.18",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "1908592895.71",
        "anchor_mixed_or_disclosed_line_name": "伺服系统类（9M累计10.08亿元混合口径，三季报未拆产品表）",
        "anchor_mixed_or_disclosed_rev_cny": "1008000000.00",
        "anchor_mixed_share_pct": "52.81",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "上海雷赛机器人(70%)、深圳灵巧驱控(100%)、东莞雷赛机器人(100%)均并表；三家子公司单体收入均未披露",
        "revenue_scope_limit": "9M独立锚定(20260930)；机器人核心部件未在分产品表单独列示，伺服系统类(9M 10.08亿/+58.64%)为通用工控+机器人混合口径，纯机器人收入金额UNKNOWN",
        "revenue_attribution": "2026Q1-Q3营收1,908.59M(+46.77%)、Q3单季661.45M(+61.70%)，伺服系统类1-9月10.08亿(+58.64%)为主力增长引擎；无框力矩电机2025年交付超12万台(+20倍)印证机器人增量真实，但不可由台数反推收入占比",
        "margin_attribution": "9M合并毛利率同比微升(M04=+0.13pp，RH05未触发)；2026H1伺服系统类毛利率28.97%(+1.34pp)，低于步进(43.85%)和控制技术(63.80%)",
        "recurring_profit_attribution": "2026Q1-Q3归母净利299.18M(+86.80%)、Q3单季105.56M(+156.10%)，盈利弹性强且未触发RH06；但机器人子公司独立盈利未直接披露（上海雷赛机器人按少数股东损益推算H1净利约1,195万，非原文直列）",
        "cash_flow_attribution": "RH04显著触发：9M经营现金流转负至-51.53M(M08=-0.1722)，Q3单季-94.89M；主因收现增速(+19.46%)远慢于收入(+46.77%)、策略性备货付现大增(+66.46%)及减少票据贴现（票据+款项融资增2.81亿、存货增2.07亿）",
        "contract_liabilities": "合同资产空白(REPORTED_BLANK，RH02待核)；存货623.67M(较年初+49.75%，三季报p2变动率列33.22%存复算差异，仅采绝对额)",
        "backlog_orders": "2026H1披露无框力矩电机在手订单超100万台（单位数口径，未折金额，严禁换算收入）；关节模组与灵巧手获近百家主流机器人客户订单",
        "cip_robot_capacity": "2026H1披露正在建设年产300万台无框力矩电机自动化产能（产能建设不等于已实现收入，在建工程明细未单列金额，留R03跟踪转固与产能利用率）",
        "attribution_verdict": "CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE",
        "r03_priority_bucket": "R03_PRIORITY_A",
        "r03_watch_points": "9M口径单独跟踪；首要盯紧Q3经营现金流转负(-9,489万)与存货/票据占款是否在高增速下持续恶化，以及机器人部件何时单列收入",
    },
    "SZ:002747": {
        "revenue_scope_tier": "MIXED_SEGMENT_DISCLOSED",
        "fy2025_total_rev_cny": "4888010963.64",
        "fy2025_mixed_or_disclosed_line_name": "工业机器人及智能制造系统（含本体/工作站/智能制造系统/Cloos）",
        "fy2025_mixed_or_disclosed_rev_cny": "3996827901.69",
        "fy2025_mixed_share_pct": "81.77",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "2577506515.40",
        "anchor_mixed_or_disclosed_line_name": "工业机器人及智能制造系统（混合口径，未单列纯本体及Cloos）",
        "anchor_mixed_or_disclosed_rev_cny": "2138349707.72",
        "anchor_mixed_share_pct": "82.96",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "Cloos(100%)、江苏鼎汇具身创新中心(54.17%)并表；埃斯顿酷卓在2026-06-30仅持股13.95%参股不并表，2026-09-08交割完成后才100%并表，严禁将酷卓1-4月收入倒算进H1",
        "revenue_scope_limit": "工业机器人及智能制造系统(82.96%)含智能制造系统集成及Cloos，核心部件(17.04%)含通用自动化，均非纯机器人本体口径；酷卓两代人形无单列收入",
        "revenue_attribution": "2026H1总营收2,577.51M，其中工业机器人及智能制造系统2,138.35M(+2.21%，占82.96%)、核心部件439.16M(-3.78%)；收入体量稳固但H1增速平缓，核心改善在毛利率而非收入放量",
        "margin_attribution": "2026H1合并毛利率同比显著提升(M04=+4.17pp，RH05未触发)；工业机器人及智能制造系统毛利率升至31.69%(+4.69pp)、核心部件升至32.40%(+1.82pp)",
        "recurring_profit_attribution": "RH06触发：2026H1归母净利161.33M中，非经常性损益高达91.15M(占56.50%)，主要为南京工艺置换南京化纤股权带来的99.50M非现金公允价值变动收益；扣非净利70.17M虽由负转正(去年同期-17.60M，改善+87.77M)，但负基数下498.64%增速不可外推",
        "cash_flow_attribution": "RH04触发：2026H1经营现金流净额44.53M，M08=0.2760；现金流调节表显示经营性应收增加(-144.94M)、经营性应付减少(-287.20M)及合同负债下降186.65M压低现金流，存货去化(+163.16M)部分对冲",
        "contract_liabilities": "2026H1合同负债由586.31M降至399.65M(-186.65M)，应收账款增至2,201.15M(+15.48%)，需在R03重点核查订单结转与回款节奏",
        "backlog_orders": "UNKNOWN（H1未披露量化在手订单金额，不填0）",
        "cip_robot_capacity": "UNKNOWN（本轮R00未单列在建工程机器人产能明细；酷卓9月并表后的整合投入留R03跟踪）",
        "attribution_verdict": "CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE",
        "r03_priority_bucket": "R03_PRIORITY_A",
        "r03_watch_points": "双警报(RH04+RH06)带入R03：剥离9,950万公允价值收益后跟踪扣非净利与毛利率持续性、应收/合同负债与现金流修复，以及酷卓并表后的实际盈亏影响",
    },
    "BJ:920593": {
        "revenue_scope_tier": "UNDISCLOSED_IN_BROADER_LINE",
        "fy2025_total_rev_cny": "267847958.21",
        "fy2025_mixed_or_disclosed_line_name": "直流电机及组件（含工业设备项目与机器人减速电机+驱控一体化）",
        "fy2025_mixed_or_disclosed_rev_cny": "42276210.55",
        "fy2025_mixed_share_pct": "15.78",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "196311538.02",
        "anchor_mixed_or_disclosed_line_name": "直流电机及组件（H1不再拆减速电机及驱控子行）",
        "anchor_mixed_or_disclosed_rev_cny": "40236521.58",
        "anchor_mixed_share_pct": "20.50",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "10家子公司并表（含美国鼎智100%、赛仑特51%自2025-12并表）；5家参股/联营公司（脉塔/锚点/联融域/华传智感/中科灵犀5%）均不并表",
        "revenue_scope_limit": "机器人收入未单列；年报正文“单项+687.23%”与附注“减速电机及驱控20.63M/+127.72%”口径无法对齐，保留UNKNOWN；H1总营收+58.92%含赛仑特并表新增47.21M（未披露机器人用途）；无框/空心杯/人形丝杠均处研究阶段",
        "revenue_attribution": "2026H1总营收196.31M(+58.92%)由三部分驱动：赛仑特并表新增47.21M（传动部件36.96M）、直流电机及组件40.24M(+202.29%，含机器人项目送样转批量)及传统电机修复；严禁把赛仑特并表增量全部归因于机器人",
        "margin_attribution": "2026H1报告披露综合毛利率45.91%(同比-6.31pp，主因低毛利直流电机30.43%与传动部件39.94%占比上升)；注：S05 M04=+15.22pp系冻结S02基期口径，R01并列呈现报告原文与冻结表差异供R03复核",
        "recurring_profit_attribution": "2026H1归母净利17.74M(-11.61%)，报告称扣除股份支付影响后归母净利2,751.15万元(+27.69%)，盈利端受股权激励费用与结构毛利下行双重影响",
        "cash_flow_attribution": "2026H1经营现金流净额50.99M(+313.66%)，M08=2.8744(优异，RH04未触发)，主因营收增加及客户预收货款大幅增加",
        "contract_liabilities": "2026H1合同负债25.70M(较期初+330.86%)，与100%时点确认收入+预收款模式及合同资产空白(RH02待核)互相印证；但两期自述存货周转时间变长（存货85.58M/+35.25%、周转率1.30）",
        "backlog_orders": "2026H1确认无应披露重大合同；未披露量化在手订单金额，留UNKNOWN",
        "cip_robot_capacity": "UNKNOWN（年报研发项目列示无框/空心杯/关节模组/人形丝杠处研究阶段，在建工程机器人产能未单列）",
        "attribution_verdict": "MIXED_OR_UNQUANTIFIED_DRIVER",
        "r03_priority_bucket": "R03_PRIORITY_A",
        "r03_watch_points": "跟踪直流电机及组件（机器人批量供货）与美国鼎智海外机器人放量持续性、赛仑特并表满周年后的内生增速及存货周转放缓风险",
    },
    "BJ:920510": {
        "revenue_scope_tier": "UNDISCLOSED_IN_BROADER_LINE",
        "fy2025_total_rev_cny": "209635220.16",
        "fy2025_mixed_or_disclosed_line_name": "产品收入（精密零部件+压铸件+谐波减速器混合口径）",
        "fy2025_mixed_or_disclosed_rev_cny": "181389268.35",
        "fy2025_mixed_share_pct": "86.53",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "132806101.91",
        "anchor_mixed_or_disclosed_line_name": "产品收入（混合口径，谐波未单列）",
        "anchor_mixed_or_disclosed_rev_cny": "108888649.05",
        "anchor_mixed_share_pct": "82.00",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "母公司及美/日全资子公司并表；拟收购51%股权的北京唯实深蓝截至2026-06-30仅付预付并购款，尚未并表",
        "revenue_scope_limit": "谐波减速器未单列，并入“产品收入”；2025年对江苏意优机器人客户销售额12,342,054.97元(占5.89%)仅保留为客户销售额事实，无交易级品类拆分，谐波及机器人单独收入留UNKNOWN",
        "revenue_attribution": "2026H1营收132.81M(+30.86%)主因半导体装备景气及加工收入恢复(+71.72%)；公司明确表述机器人板块“由试样送样向小批量稳定供货转型、板块整体经营规模保持平稳”，本期收入改善不能归因于机器人",
        "margin_attribution": "2026H1合并毛利率29.65%(M04=+2.59pp)，主要由加工收入毛利率大升(+15.28pp至42.65%)拉动，产品收入毛利率反降0.65pp至25.01%",
        "recurring_profit_attribution": "2025全年亏损(-15.55M)，2026H1扭亏至3.50M（上年同期-1.50M，低基数扭亏），盈利基础仍偏薄",
        "cash_flow_attribution": "2026H1经营现金流20.38M(M08=5.8301，RH04未触发)，但同比-21.78%；另因收购唯实深蓝预付并购款8,040万并新增并购贷5,624万",
        "contract_liabilities": "合同资产连续两期空白(REPORTED_BLANK，RH02待核)；存货63.09M(+10.53%)，周转天数115.8天较FY2025加快",
        "backlog_orders": "UNKNOWN（未披露谐波减速器量化在手订单金额或台数，不填0）",
        "cip_robot_capacity": "UNKNOWN（具备03-32型谐波量产能力，但未单列在建工程对应谐波产能投入金额）",
        "attribution_verdict": "NON_ROBOT_OR_QUALITY_CAVEAT",
        "r03_priority_bucket": "R03_OBSERVE_OR_DEFER",
        "r03_watch_points": "观察列：待谐波减速器从小批量进入放量且单列收入、以及唯实深蓝并表落地后再重估进R03",
    },
    "BJ:920491": {
        "revenue_scope_tier": "MIXED_SEGMENT_DISCLOSED",
        "fy2025_total_rev_cny": "683315916.15",
        "fy2025_mixed_or_disclosed_line_name": "传感器大类（文本披露应用于机器人的传感器超1.1亿元，未拆分服务/工业/人形）",
        "fy2025_mixed_or_disclosed_rev_cny": "573346877.74",
        "fy2025_mixed_share_pct": "83.91",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "317600534.77",
        "anchor_mixed_or_disclosed_line_name": "传感器大类（2026H1未披露机器人传感器金额）",
        "anchor_mixed_or_disclosed_rev_cny": "259908040.51",
        "anchor_mixed_share_pct": "81.84",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "肇庆/香港/江西奥迪威并表；“广州奥迪威机器人”实为专用自动化设备(非机器人本体)；电子皮肤主体奥感微为联营参股不并表(2026H1营收仅12,648.14元、净亏315.95万)",
        "revenue_scope_limit": "FY2025文本称机器人传感器超1.1亿元(主体为扫地/服务机器人超声波传感器，非表格科目)；2026H1未披露机器人传感器金额；柔性电子皮肤在参股公司奥感微不并表且基本无收入",
        "revenue_attribution": "2026H1总营收317.60M(-3.80%)，传感器大类259.91M(-5.73%)，公司归因下游服务机器人竞争加剧降价及智能仪表海外客户订单减少；虽服务机器人Q2环比+58.11%，但H1整体呈负增长",
        "margin_attribution": "RH05触发：2026H1综合毛利率降2.53pp至32.89%(M04=-2.54pp)，传感器毛利率降2.43pp至34.84%，系服务机器人供应链降价压力、贵金属涨价与汇兑损失共同所致",
        "recurring_profit_attribution": "2026H1净利润29.05M(-42.44%)，营收微降叠加毛利承压与参股公司亏损(-277万权益法投资损失)放大净利降幅",
        "cash_flow_attribution": "2026H1经营现金流47.89M(+7.71%)，M08=1.6484(正常，RH04未触发)，回款纪律保持稳健",
        "contract_liabilities": "合同资产连续两期空白(REPORTED_BLANK，RH02待核)；存货85.24M(+7.07%)，周转天数69.6天无积压",
        "backlog_orders": "UNKNOWN（未披露量化在手订单金额，不填0）",
        "cip_robot_capacity": "UNKNOWN（电子皮肤主体奥感微不并表，母体未单列人形/工业机器人传感器在建产能）",
        "attribution_verdict": "NON_ROBOT_OR_QUALITY_CAVEAT",
        "r03_priority_bucket": "R03_OBSERVE_OR_DEFER",
        "r03_watch_points": "观察列：服务机器人传感器面临降价压力且电子皮肤在参股公司尚未起量，暂不优先进入R03",
    },
    "SH:688003": {
        "revenue_scope_tier": "MIXED_SEGMENT_DISCLOSED",
        "fy2025_total_rev_cny": "1789803456.66",
        "fy2025_mixed_or_disclosed_line_name": "具身智能方案（含机器人大脑域控与商用车L4域控混合口径）",
        "fy2025_mixed_or_disclosed_rev_cny": "177957098.78",
        "fy2025_mixed_share_pct": "9.94",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "1485588803.39",
        "anchor_mixed_or_disclosed_line_name": "9M未拆具身分部；2026H1具身大脑方案157.69M（占H1营收17.77%，含商用车L4域控）",
        "anchor_mixed_or_disclosed_rev_cny": "UNKNOWN_9M_SEE_H1_157691400.00",
        "anchor_mixed_share_pct": "UNKNOWN_9M_SEE_H1_17.77",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "苏州天准星智持股76.40%并表（2026H1营收152.29M、净利6.32M、经营现金流-105.29M）；苏州矽行半导体参股不并表",
        "revenue_scope_limit": "9M独立锚定(20260930)，三季报全篇未提具身/机器人；2026H1具身大脑方案157.69M(+141.60%)混含无人物流车/Robotaxi/重卡等商用车L4域控，纯人形机器人收入UNKNOWN",
        "revenue_attribution": "2026Q1-Q3营收1,485.59M(+52.07%)、Q3单季598.45M(+57.46%)；按H1分部看AI量检测(42.24%/+28.85%)、AI制程(39.99%/+47.31%)与具身大脑(17.77%/+141.60%)三线齐升，具身是高弹性增量但非唯一驱动",
        "margin_attribution": "9M合并毛利率微升(M04=+0.27pp，RH05未触发)；但具身智能方案FY2025毛利率仅21.03%(-8.54pp)，2026H1未披露该分部毛利率（天准星智H1净利率约4.1%），盈利能力偏薄",
        "recurring_profit_attribution": "RH06触发：9M归母净利66.46M中扣非仅21.47M(占32.31%)，非经常性损益44.98M(占67.69%，含金融资产公允价值变动+51.32M)；Q3单季归母亏32.03M主因金融资产公允价值变动-44.89M（期间费用增长亦被原文提及），Q3扣非仍为正+11.13M",
        "cash_flow_attribution": "9M合并经营现金流96.99M(+209.89%，M08=1.4594，RH04未触发)；但须注意核心具身子公司天准星智2026H1单体经营现金流为-105.29M，具身业务资金占用高",
        "contract_liabilities": "RH02触发：9M末存货飙升至2,083.13M(较年初+75.01%，M11=+37.36天，三季报未说明增幅原因)，合同资产73.25M(+40.03%，质保金性质)；公司自认2023-2025存货周转率1.02处于低位",
        "backlog_orders": "2026H1披露集团新签订单21.04亿(+62.20%)、期末在手订单23.75亿(+49.61%)；其中具身大脑新签315.24M(+229.74%)，订单数据明确但未拆分人形 vs 商用车占比",
        "cip_robot_capacity": "UNKNOWN（本轮R00未单列在建工程对应具身域控产能明细，留R03跟踪）",
        "attribution_verdict": "CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE",
        "r03_priority_bucket": "R03_PRIORITY_A",
        "r03_watch_points": "9M口径单独跟踪；带入R03三项硬观察：纯人形与商用车域控拆分、9M存货暴增75%与天准星智现金流(-1.05亿)周转压力、以及金融资产波动对归母净利的干扰",
    },
    "SZ:002698": {
        "revenue_scope_tier": "MIXED_SEGMENT_DISCLOSED",
        "fy2025_total_rev_cny": "2828078579.62",
        "fy2025_mixed_or_disclosed_line_name": "机器人+（含炉前作业机器人、电石智能工厂整线、圆盘浇铸机等）",
        "fy2025_mixed_or_disclosed_rev_cny": "33145372.72",
        "fy2025_mixed_share_pct": "1.17",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "1368574570.01",
        "anchor_mixed_or_disclosed_line_name": "机器人+（单列但含整线/非单机，毛利率14.87%）",
        "anchor_mixed_or_disclosed_rev_cny": "48166263.71",
        "anchor_mixed_share_pct": "3.52",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "“机器人+”在母公司体系确认；医疗手术机器人思哲睿(13.43%)权益法参股不并表；灵博机器人属2026-08拟增资2,000万元拟持股12%未交割事项（截至H1尚未出资、尚未参股，交割及会计处理待核）；哈工大人形合作项目已终止",
        "revenue_scope_limit": "“机器人+”虽单列但含电石智能工厂整线等，且体量仅占总收入1.17%(FY25)/3.52%(H1)，纯本体未拆；与哈工大合作人形项目2026H1已终止，无收入、无并表主体",
        "revenue_attribution": "2026H1总营收1,368.57M(+0.49%)几乎持平，主业为石化/化工后处理智能制造装备(66.78%)与工业服务(27.35%)；“机器人+”仅48.17M(占3.52%)，对公司整体营收几乎无实质拉动",
        "margin_attribution": "RH05触发(M04=-2.28pp)：2026H1智能制造装备毛利率降2.90pp、环保降26.84pp，“机器人+”因新品类出炉机器人成本过高亏损将毛利率拉低至14.87%(-3.71pp)；仅工业服务毛利率修复至27.80%",
        "recurring_profit_attribution": "2026H1归母净利234.54M(-15.44%)、扣非218.47M(-16.02%)，主业盈利呈下行态势",
        "cash_flow_attribution": "2026H1经营现金流239.83M(+1,585.27%，M08=1.0225，RH04未触发)，现金流改善主要来自主业装备回款，与机器人业务无关",
        "contract_liabilities": "S05 M12=-4.89pp、M11=-23.33天，存货与合同资产未触发警报，但主要对应石化后处理成套装备",
        "backlog_orders": "UNKNOWN（未单列“机器人+”在手订单金额，不填0）",
        "cip_robot_capacity": "UNKNOWN（哈工大人形联合研发项目已终止，无量产产能建设）",
        "attribution_verdict": "NON_ROBOT_OR_QUALITY_CAVEAT",
        "r03_priority_bucket": "R03_OBSERVE_OR_DEFER",
        "r03_watch_points": "观察/延后列：人形项目已明确终止、“机器人+”占比仅3.5%且毛利率跌至14.87%，不建议作为R03核心拐点标的",
    },
    "BJ:920578": {
        "revenue_scope_tier": "MIXED_SEGMENT_DISCLOSED",
        "fy2025_total_rev_cny": "165348469.22",
        "fy2025_mixed_or_disclosed_line_name": "机器人自动线产品（项目制系统集成，含外购发那科本体与自制桁架）",
        "fy2025_mixed_or_disclosed_rev_cny": "142296714.12",
        "fy2025_mixed_share_pct": "86.06",
        "fy2025_pure_robot_rev_cny": "UNKNOWN",
        "anchor_total_rev_cny": "100212170.10",
        "anchor_mixed_or_disclosed_line_name": "机器人自动化生产线（系统集成混合口径，未拆本体与集成）",
        "anchor_mixed_or_disclosed_rev_cny": "84703834.75",
        "anchor_mixed_share_pct": "84.52",
        "anchor_pure_robot_rev_cny": "UNKNOWN",
        "consolidation_boundary_note": "母公司为主体，蓝杰公司(钣金)与巨能未来(软件)全资并表；2025年前五大供应商含上海发那科机器人8.03M(占8.63%)，印证存在本体外购",
        "revenue_scope_limit": "84.52%收入为项目制系统集成产线，未拆分外购本体、自制桁架与集成服务，纯自产机器人本体收入UNKNOWN",
        "revenue_attribution": "营收连续收缩：FY2025总营收-34.54%（自动线-38.98%），2026H1总营收100.21M(-12.29%)、机器人自动化生产线84.70M(-16.95%)，业务规模处于下行通道",
        "margin_attribution": "2026H1合并毛利率28.85%(M04=+5.59pp)，机器人自动化生产线毛利率升6.79pp至29.32%，是扭亏主因，但属收入萎缩背景下的项目结构修复",
        "recurring_profit_attribution": "2026H1归母净利10.06M(+176.27%)、扣非6.97M(+318.32%)，非经常性损益3.09M占归母30.7%(主要来自政府补助)，扭亏质量部分依赖补助与减值减少",
        "cash_flow_attribution": "RH04触发：2026H1经营现金流仅1.67M(-94.52%)，M08=0.1658；除上年单笔超3,000万验收款高基数外，本期应收票据+38.07%、合同负债大降34.59%显示回款偏票据且新单不足",
        "contract_liabilities": "2026H1合同负债24.34M(较年初-34.59%)，公司明确解释“新合同订单的增长小于订单逐步转入收入的幅度，导致预收款减少”，存量订单消耗信号明显",
        "backlog_orders": "UNKNOWN（未披露期末在手订单金额，仅合同负债降34.59%侧面提示新签不足）",
        "cip_robot_capacity": "UNKNOWN（无机器人本体扩产在建工程披露）",
        "attribution_verdict": "NON_ROBOT_OR_QUALITY_CAVEAT",
        "r03_priority_bucket": "R03_OBSERVE_OR_DEFER",
        "r03_watch_points": "观察/延后列：营收负增长(-12.3%)、系统集成属性强、经营现金流/净利仅0.166且合同负债降34.6%，暂不优先进入R03",
    },
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_lf_bytes(path: pathlib.Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def write_lf_text(path: pathlib.Path, text: str) -> bytes:
    data = text.replace("\r\n", "\n").encode("utf-8")
    path.write_bytes(data)
    return data


def write_lf_csv(path: pathlib.Path, fieldnames: list, rows: list) -> bytes:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    data = buf.getvalue().encode("utf-8")
    path.write_bytes(data)
    return data


def load_csv_map(rel: str, key_col: str) -> dict:
    out = {}
    with (ROOT / rel).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out[row[key_col]] = row
    return out


def main() -> int:
    R01_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Read Git-tracked inputs
    release = json.loads((ROOT / "runs/issues/R01/release_20261126.json").read_text(encoding="utf-8"))
    r00_acc = json.loads((ROOT / "runs/issues/R00/acceptance_r00_batch01_02_20261126.json").read_text(encoding="utf-8"))
    r00_dispatch = load_csv_map("runs/issues/R00/business_batch_dispatch.csv", "security_id")
    r00_reg = load_csv_map("runs/issues/R00/business_review_register.csv", "security_id")
    s08_map = load_csv_map("runs/issues/S08/business_verification_candidates.csv", "security_id")
    s05_log = load_csv_map("runs/issues/S05/quality_decision_log.csv", "security_id")
    meth = json.loads((ROOT / "data/methodology_decision_20261107.json").read_text(encoding="utf-8"))

    # S05 quality flags indexed by (sid, metric_id)
    s05_flags = {}
    with (ROOT / "runs/issues/S05/quality_flags.csv").open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sid = row["security_id"]
            if sid in COMPANY_ATTRIBUTION:
                s05_flags.setdefault(sid, {})[row["metric_id"]] = {
                    "rh": row["rh"],
                    "metric_value": row["metric_value"],
                    "metric_unit": row["metric_unit"],
                    "metric_status": row["metric_status"],
                    "rh_status": row["rh_status"],
                    "evidence_document_ids": row["evidence_document_ids"],
                    "evidence_pages": row["evidence_pages"],
                }

    # S02 key growth/margin/profit metrics at anchor period
    s02_anchor_metrics = {}
    target_anchor = {sid: r00_reg[sid]["anchor_period"] for sid in COMPANY_ATTRIBUTION}
    with (ROOT / "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv").open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sid = row["security_id"]
            if sid in target_anchor and row["period_key"] == target_anchor[sid]:
                mid = row["metric_id"]
                if mid in ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M10", "M11", "M12"):
                    s02_anchor_metrics.setdefault(sid, {})[mid] = {
                        "metric_name_cn": row["metric_name_cn"],
                        "value": row["value"],
                        "unit": row["unit"],
                        "metric_status": row["metric_status"],
                    }

    # Build ordered 10-company list from release child_issues
    ordered = []
    for ci in release["child_issues"]:
        for sid in ci["companies"]:
            ordered.append((ci["batch_id"], ci["issue_number"], ci["r00_child_issue_number"], sid))

    # 2. financial_attribution_dispatch.csv
    dispatch_rows = []
    for batch_id, r01_issue, r00_issue, sid in ordered:
        rr = r00_reg[sid]
        rd = r00_dispatch[sid]
        ap = rr["anchor_period"]
        dispatch_rows.append({
            "batch_id": batch_id,
            "child_issue_number": str(r01_issue),
            "r00_child_issue_number": str(r00_issue),
            "security_id": sid,
            "stock_name": rr["stock_name"],
            "anchor_period": ap,
            "anchor_group": "H1_20260630" if ap == "20260630" else "9M_20260930",
            "s08_priority_tier": rd["s08_priority_tier"],
            "r00_robot_exposure": rr["robot_exposure_verdict"],
            "r00_commercial_stage": rr["commercial_stage_verdict"],
            "s05_rh_triggers": rd["s05_rh_triggers"],
            "s05_pending_flags": rd["s05_pending_flags"],
            "legacy_auto_promoted": rd["legacy_auto_promoted"],
            "dispatch_status": "ATTRIBUTED_SELF_CHECK",
        })
    dispatch_cols = list(dispatch_rows[0].keys())
    write_lf_csv(R01_DIR / "financial_attribution_dispatch.csv", dispatch_cols, dispatch_rows)

    # 3. robot_revenue_scope.csv
    scope_rows = []
    for batch_id, _, _, sid in ordered:
        rr = r00_reg[sid]
        ca = COMPANY_ATTRIBUTION[sid]
        scope_rows.append({
            "security_id": sid,
            "stock_name": rr["stock_name"],
            "batch_id": batch_id,
            "anchor_period": rr["anchor_period"],
            "knowledge_as_of": KNOWLEDGE_AS_OF,
            "revenue_scope_tier": ca["revenue_scope_tier"],
            "fy2025_total_rev_cny": ca["fy2025_total_rev_cny"],
            "fy2025_mixed_or_disclosed_line_name": ca["fy2025_mixed_or_disclosed_line_name"],
            "fy2025_mixed_or_disclosed_rev_cny": ca["fy2025_mixed_or_disclosed_rev_cny"],
            "fy2025_mixed_share_pct": ca["fy2025_mixed_share_pct"],
            "fy2025_pure_robot_rev_cny": ca["fy2025_pure_robot_rev_cny"],
            "anchor_total_rev_cny": ca["anchor_total_rev_cny"],
            "anchor_mixed_or_disclosed_line_name": ca["anchor_mixed_or_disclosed_line_name"],
            "anchor_mixed_or_disclosed_rev_cny": ca["anchor_mixed_or_disclosed_rev_cny"],
            "anchor_mixed_share_pct": ca["anchor_mixed_share_pct"],
            "anchor_pure_robot_rev_cny": ca["anchor_pure_robot_rev_cny"],
            "consolidation_boundary_note": ca["consolidation_boundary_note"],
            "non_consolidated_excluded": rr["non_consolidated_entities_excluded"],
            "revenue_scope_limit": ca["revenue_scope_limit"],
        })
    scope_cols = list(scope_rows[0].keys())
    write_lf_csv(R01_DIR / "robot_revenue_scope.csv", scope_cols, scope_rows)

    # 4. attribution_review.json
    companies_json = []
    priority_a = []
    observe_defer = []
    for batch_id, r01_issue, r00_issue, sid in ordered:
        rr = r00_reg[sid]
        ca = COMPANY_ATTRIBUTION[sid]
        entry = {
            "security_id": sid,
            "stock_name": rr["stock_name"],
            "batch_id": batch_id,
            "child_issue_number": r01_issue,
            "r00_child_issue_number": r00_issue,
            "anchor_period": rr["anchor_period"],
            "anchor_group": "H1_20260630" if rr["anchor_period"] == "20260630" else "9M_20260930",
            "knowledge_as_of": KNOWLEDGE_AS_OF,
            "revenue_scope": {
                "tier": ca["revenue_scope_tier"],
                "fy2025_total_rev_cny": ca["fy2025_total_rev_cny"],
                "fy2025_mixed_or_disclosed_rev_cny": ca["fy2025_mixed_or_disclosed_rev_cny"],
                "fy2025_pure_robot_rev_cny": ca["fy2025_pure_robot_rev_cny"],
                "anchor_total_rev_cny": ca["anchor_total_rev_cny"],
                "anchor_mixed_or_disclosed_rev_cny": ca["anchor_mixed_or_disclosed_rev_cny"],
                "anchor_pure_robot_rev_cny": ca["anchor_pure_robot_rev_cny"],
                "consolidation_boundary_note": ca["consolidation_boundary_note"],
                "non_consolidated_excluded": rr["non_consolidated_entities_excluded"],
                "limit": ca["revenue_scope_limit"],
            },
            "financial_metrics_from_s02_s05": {
                "s05_quality_flags": s05_flags[sid],
                "s02_anchor_metrics": s02_anchor_metrics.get(sid, {}),
                "s05_surviving_dimensions": s05_log[sid].get("surviving_dimensions", ""),
                "s05_rh_triggers": r00_dispatch[sid]["s05_rh_triggers"],
                "s05_pending_flags": r00_dispatch[sid]["s05_pending_flags"],
            },
            "four_pillar_attribution": {
                "revenue_attribution": ca["revenue_attribution"],
                "margin_attribution": ca["margin_attribution"],
                "recurring_profit_attribution": ca["recurring_profit_attribution"],
                "cash_flow_attribution": ca["cash_flow_attribution"],
            },
            "leading_indicators_check": {
                "methodology_id": meth.get("decision_id", "METHOD_20261107_LEADING_INDICATORS"),
                "contract_liabilities": ca["contract_liabilities"],
                "backlog_orders": ca["backlog_orders"],
                "cip_robot_capacity": ca["cip_robot_capacity"],
            },
            "attribution_verdict": ca["attribution_verdict"],
            "r03_priority_bucket": ca["r03_priority_bucket"],
            "r03_watch_points": ca["r03_watch_points"],
            "attribution_limits": rr["key_unknowns_and_limits"],
        }
        companies_json.append(entry)
        if ca["r03_priority_bucket"] == "R03_PRIORITY_A":
            priority_a.append(f"{sid} {rr['stock_name']}")
        else:
            observe_defer.append(f"{sid} {rr['stock_name']}")

    attr_doc = {
        "artifact": "R01_FINANCIAL_ATTRIBUTION_AND_REVENUE_SCOPE",
        "issue_key": "R01",
        "issue_number": 45,
        "child_issues": [59, 60],
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "fixed_now": FIXED_NOW,
        "upstream_r00_acceptance": {
            "file": "runs/issues/R00/acceptance_r00_batch01_02_20261126.json",
            "decision": r00_acc["decision"],
            "reviewed_commit": r00_acc["reviewed_version"]["commit"],
        },
        "methodology_ref": meth.get("decision_id", "METHOD_20261107_LEADING_INDICATORS"),
        "anchor_separation": {
            "h1_20260630_count": sum(1 for c in companies_json if c["anchor_period"] == "20260630"),
            "m9_20260930_count": sum(1 for c in companies_json if c["anchor_period"] == "20260930"),
            "h1_companies": [c["security_id"] for c in companies_json if c["anchor_period"] == "20260630"],
            "m9_companies": [c["security_id"] for c in companies_json if c["anchor_period"] == "20260930"],
            "cross_period_merge_prohibited": True,
        },
        "r03_candidate_tiering": {
            "disclaimer": "仅用于 R03（行业与公司拐点研究）排包优先序，不构成投资评级或买卖建议。",
            "R03_PRIORITY_A": priority_a,
            "R03_OBSERVE_OR_DEFER": observe_defer,
        },
        "companies": companies_json,
    }
    write_lf_text(R01_DIR / "attribution_review.json", json.dumps(attr_doc, ensure_ascii=False, indent=2) + "\n")

    # 5. handoff.md
    md_lines = [
        "# R01（#45）财务归因与收入范围核验交接说明（#59 Batch 01 + #60 Batch 02 共 10 家）",
        "",
        f"- 计划版本：`20261026_collection_first_v2`；知识截止日：`{KNOWLEDGE_AS_OF}`；固定重跑时间：`{FIXED_NOW}`",
        "- 复核性质：`SELF_CHECK`（不冒充独立验收；待 Codex 干净树独立复核）",
        "- 覆盖范围：10 家 R00 已独立验收的 `TIER_1` 公司，严格拆分为 8 家 H1（`20260630`）与 2 家 9M（`20260930`：雷赛智能、天准科技），严禁跨期合并。",
        "- 方法论遵循：`METHOD_20261107_LEADING_INDICATORS`（合同负债/在手订单/在建工程独立留痕，未披露留 `UNKNOWN` 不填 0）。",
        "- 放行守卫：`R03_released=false`、`R04_started=false`、`#53 OPEN` 未触碰。",
        "",
        "## 1. 复现命令",
        "```powershell",
        f"$env:R01_FIXED_NOW='{FIXED_NOW}'; py runs/issues/R01/step_r01_build.py; py runs/issues/R01/step_r01_verify.py",
        "```",
        "",
        "## 2. 10 家公司收入范围与归因分层一览",
        "",
        "| 批次 | 代码 | 名称 | 锚定期 | 收入口径层级 | 锚定期纯本体收入 | S05 质量项 | 归因判定 | R03 排包建议 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in companies_json:
        sid = c["security_id"]
        tr = c["financial_metrics_from_s02_s05"]["s05_rh_triggers"] or "无"
        pd = c["financial_metrics_from_s02_s05"]["s05_pending_flags"] or "无"
        md_lines.append(
            f"| `{c['batch_id']}` | `{sid}` | {c['stock_name']} | `{c['anchor_period']}` | "
            f"`{c['revenue_scope']['tier']}` | `{c['revenue_scope']['anchor_pure_robot_rev_cny']}` | "
            f"触发:{tr} / 待核:{pd} | `{c['attribution_verdict']}` | `{c['r03_priority_bucket']}` |"
        )
    md_lines += [
        "",
        "## 3. R03 优先候选与观察/延后分层（仅研究排包，非投资建议）",
        f"- **`R03_PRIORITY_A`（6 家）**：{', '.join(priority_a)}",
        f"- **`R03_OBSERVE_OR_DEFER`（4 家）**：{', '.join(observe_defer)}",
        "",
        "## 4. 关键结转限制条款",
        "- 10 家公司在各自锚定期（2026H1 / 2026Q1-Q3）均未单列纯机器人本体收入（`anchor_pure_robot_rev_cny=UNKNOWN`）；FY2025 仅拓斯达单列机器人本体 300,432,856.32 元。",
        "- 双环传动 2026H1 的 4.40 亿元归属“减速器及其他”混合科目；丰光精密 2025 年对意优机器人客户销售额 1,234.21 万元（5.89%）仅作客户销售额事实记录；博实股份灵博机器人属 2026-08 拟增资未交割事项（截至 H1 尚未出资、尚未参股，交割及会计处理待核）。",
        "- 严禁由在手订单台数（如雷赛 100 万台）或产能规划（如 300 万台）反推实绩收入；未披露在建工程/在手订单一律保留 `UNKNOWN`。",
    ]
    write_lf_text(R01_DIR / "handoff.md", "\n".join(md_lines) + "\n")

    # 6. Dynamic self-checks (zero hardcoded PASS)
    anomalies = []
    checks = []

    def add_check(cid: str, name: str, ok: bool, detail: str):
        checks.append({"id": cid, "name": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            anomalies.append(f"{cid}: {detail}")

    # C01: 10 companies, 5+5 mutually exclusive, match R00 accepted
    sids = [x[3] for x in ordered]
    r00_sids = list(r00_reg.keys())
    c01_ok = len(sids) == 10 and len(set(sids)) == 10 and set(sids) == set(r00_sids)
    add_check("C01", "10 家名单与 #59/#60 及 R00 验收名单完全一致且互斥零重复", c01_ok, f"count={len(sids)} unique={len(set(sids))}")

    # C02: Anchor separation 8 H1 + 2 9M
    h1_cnt = sum(1 for c in companies_json if c["anchor_period"] == "20260630")
    m9_cnt = sum(1 for c in companies_json if c["anchor_period"] == "20260930")
    c02_ok = h1_cnt == 8 and m9_cnt == 2 and all(c["anchor_period"] == s08_map[c["security_id"]]["s05_anchor_period"] for c in companies_json)
    add_check("C02", "8 家 H1 与 2 家 9M 锚定期严格分离并与 S08/R00 一致", c02_ok, f"h1={h1_cnt} m9={m9_cnt}")

    # C03: Pure robot revenue discipline
    bad_pure = [r["security_id"] for r in scope_rows if r["anchor_pure_robot_rev_cny"] != "UNKNOWN"]
    fy25_pure_non_unk = {r["security_id"]: r["fy2025_pure_robot_rev_cny"] for r in scope_rows if r["fy2025_pure_robot_rev_cny"] != "UNKNOWN"}
    c03_ok = len(bad_pure) == 0 and fy25_pure_non_unk == {"SZ:300607": "300432856.32"}
    add_check("C03", "锚定期纯机器人本体收入全部 UNKNOWN，FY2025 仅拓斯达单列 300432856.32", c03_ok, f"bad_anchor={bad_pure} fy25_disclosed={fy25_pure_non_unk}")

    # C04: Zero-regression forbidden phrase guard
    hits = []
    for fname in ["robot_revenue_scope.csv", "attribution_review.json", "handoff.md"]:
        txt = (R01_DIR / fname).read_text(encoding="utf-8")
        for p in FORBIDDEN_PHRASES:
            if p in txt:
                hits.append(f"{fname}:{p}")
    add_check("C04", "口径零回退守卫（双环/丰光/博实禁用表述 0 命中）", len(hits) == 0, f"hits={hits}")

    # C05: S05 exact match
    s05_bad = []
    for c in companies_json:
        sid = c["security_id"]
        for mid in ("M04", "M08", "M10", "M11", "M12"):
            if mid not in c["financial_metrics_from_s02_s05"]["s05_quality_flags"]:
                s05_bad.append(f"{sid}:{mid}")
    add_check("C05", "10 家公司 S05 五项质量指标(M04/M08/M10/M11/M12)完整挂接", len(s05_bad) == 0, f"missing={s05_bad}")

    # C06: Leading indicators populated
    li_bad = []
    for c in companies_json:
        li = c["leading_indicators_check"]
        for k in ("contract_liabilities", "backlog_orders", "cip_robot_capacity"):
            if not li.get(k):
                li_bad.append(f"{c['security_id']}:{k}")
    add_check("C06", "需求先行指标(合同负债/在手订单/在建工程)按 METHOD_20261107 完整登记", len(li_bad) == 0, f"missing={li_bad}")

    # C07: Inputs all inside Git working tree
    missing_in = [p for p in INPUT_PATHS if not (ROOT / p).exists()]
    add_check("C07", "全部 15 份输入存在且位于 Git 工作树内", len(missing_in) == 0, f"inputs={len(INPUT_PATHS)} missing={missing_in}")

    # 7. manifest.json (compute after all other deliverables are written)
    input_entries = []
    for rel in INPUT_PATHS:
        b = read_lf_bytes(ROOT / rel)
        input_entries.append({"path": rel, "bytes": len(b), "sha256": sha256_bytes(b)})

    deliv_paths = [
        "runs/issues/R01/financial_attribution_dispatch.csv",
        "runs/issues/R01/robot_revenue_scope.csv",
        "runs/issues/R01/attribution_review.json",
        "runs/issues/R01/handoff.md",
        "runs/issues/R01/step_r01_build.py",
    ]
    if (R01_DIR / "step_r01_verify.py").exists():
        deliv_paths.append("runs/issues/R01/step_r01_verify.py")

    deliv_entries = []
    for rel in sorted(deliv_paths):
        b = (ROOT / rel).read_bytes()
        deliv_entries.append({"path": rel, "bytes": len(b), "sha256": sha256_bytes(b)})

    root_digest = sha256_bytes("\n".join(f"{d['path']}:{d['sha256']}" for d in deliv_entries).encode("utf-8"))
    manifest = {
        "artifact": "R01_DELIVERY_MANIFEST",
        "issue_key": "R01",
        "issue_number": 45,
        "child_issues": [59, 60],
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "executor": "Antigravity (direct intervention)",
        "review_nature": "SELF_CHECK",
        "fixed_now": FIXED_NOW,
        "input_hash_basis": "CANONICAL_LF_BYTES",
        "deliverable_hash_basis": "EXACT_BYTES_LF",
        "root_digest_basis": "sorted deliverables 'path:sha256' joined by \\n, sha256; excludes manifest.json & review.json",
        "manifest_root_digest": root_digest,
        "input_count": len(input_entries),
        "deliverable_count": len(deliv_entries),
        "inputs": input_entries,
        "deliverables": deliv_entries,
        "anomaly_count": len(anomalies),
    }
    write_lf_text(R01_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    # 8. review.json (dynamic decision)
    decision = "SELF_CHECK_PASS_WITH_LIMITS" if len(anomalies) == 0 else "NOT_ACCEPTED_PENDING_FIX"
    review = {
        "artifact": "R01_SELF_CHECK_REVIEW",
        "issue_key": "R01",
        "issue_number": 45,
        "child_issues": [59, 60],
        "plan_version": "20261026_collection_first_v2",
        "reviewed_on": "2026-11-26",
        "timezone": "Asia/Shanghai",
        "review_nature": "SELF_CHECK",
        "executor": "Antigravity (direct intervention)",
        "reviewer_assigned": "Codex",
        "decision_rule": "anomalies 为空 -> SELF_CHECK_PASS_WITH_LIMITS；任一阻塞异常 -> NOT_ACCEPTED_PENDING_FIX",
        "anomalies": anomalies,
        "decision": decision,
        "checks_summary": f"{sum(1 for c in checks if c['result']=='PASS')}/{len(checks)} PASS",
        "checks": checks,
        "counts": {
            "companies": len(companies_json),
            "h1_anchor": h1_cnt,
            "m9_anchor": m9_cnt,
            "r03_priority_a": len(priority_a),
            "r03_observe_or_defer": len(observe_defer),
        },
        "R03_released": False,
        "R04_started": False,
        "issue_53_touched": False,
        "issue_53_status": "OPEN",
        "independent_review_required": True,
        "independent_review_status": "PENDING_CODEX_INDEPENDENT_REVIEW",
    }
    write_lf_text(R01_DIR / "review.json", json.dumps(review, ensure_ascii=False, indent=2) + "\n")

    print(f"R01 build done @ {FIXED_NOW}")
    print(f"companies={len(companies_json)} (H1={h1_cnt}, 9M={m9_cnt}) | R03_PRIORITY_A={len(priority_a)} | OBSERVE_DEFER={len(observe_defer)}")
    print(f"checks {review['checks_summary']} decision={decision} manifest_root_digest={root_digest}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
