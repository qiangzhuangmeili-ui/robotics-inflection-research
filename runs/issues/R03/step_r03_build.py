#!/usr/bin/env python3
"""Deterministic builder for #47 R03 (#63 R03_BATCH_01 + #64 R03_BATCH_02, 6 core TIER_1 companies)."""

import csv
import hashlib
import io
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
R03_DIR = ROOT / "runs" / "issues" / "R03"
FIXED_NOW = os.environ.get("R03_FIXED_NOW", "2026-11-28T00:02:00+08:00")
KNOWLEDGE_AS_OF = "2026-10-25"

INPUT_PATHS = [
    "runs/issues/R03/release_20261127.json",
    "runs/issues/R01/acceptance_r01_20261126.json",
    "runs/issues/R01/attribution_review.json",
    "runs/issues/R01/robot_revenue_scope.csv",
    "runs/issues/R02/acceptance_r02_20261126.json",
    "runs/issues/R02/industry_signals.csv",
    "runs/issues/R02/industry_limits.md",
    "runs/issues/R00/tier1_completion/acceptance_r00_tier1_complete_20261127.json",
]

CASES = {
    "SZ:300607": {
        "r02_topic_id": "R02_T02",
        "product_line_separation": "已量产收入线：工业机器人及自动化应用系统（FY25 6.85亿含本体3.00亿+集成3.85亿；2026H1 7.07亿/+121.62%，未拆纯本体）；早期验证线：人形机器人小拓（客户场景小批量验证，独立收入未披露/UNKNOWN）、四足星仔（样机阶段，独立收入未披露/UNKNOWN）、矩阵智拓（51%并表AI算法，FY25亏343万，独立收入未披露/UNKNOWN）。严禁以小拓或星仔代表公司主业阶段。",
        "two_period_comparable_facts": "同报告期H1对比(2025H1 vs 2026H1)：工业机器人及自动化应用系统2026H1直接披露7.07亿(同比+121.62%，按同比复算2025H1约3.19亿)，板块毛利率2026H1直接披露30.75%(同比-10.46pp，复算2025H1约41.21%)；集团总营收2026H1直接披露12.88亿(S02 M01同比+18.61%，复算2025H1约10.86亿)，合并毛利率M04=+1.68pp，2026H1经营现金流直接披露1.47亿(M08=1.41)；2026H1工业机器人签单约6,800台、出货约5,500台、自产多关节收入同比+22.21%。【全年背景单列，不与H1直比】FY25全年该板块6.85亿(-9.24%，毛利率35.84%)。",
        "alternative_explanations": "①集成化低毛利放量：2026H1收入翻倍主要由自动化应用系统与3C大客户合作推动，板块毛利率大降10.46pp，并非高毛利纯本体爆发；②合并毛利率改善主要来自主动收缩低毛利智能能源及环境管理系统业务（FY25全年9.15亿，2026H1约0.70亿，属全年与半年的结构体量对照、非同报告期同比，依R00已核年报/半年报分部口径），属业务收缩效应；③3C客户资本开支具强周期性，单一周期脉冲不等同持续拐点。",
        "falsifiers": "F1：2026H2/全年工业机器人及自动化应用系统毛利率继续跌破28%或收入同比转负；F2：自产多关节机器人增速回落至个位数且3C大客户订单退坡；F3：应收账款及合同资产反弹导致M08经营现金流/净利跌破0.7。",
        "evidence_gaps": "G1：2026H1未拆分机器人本体与自动化应用系统各自金额及毛利率；G2：人形小拓、X5控制平台与矩阵智拓均无独立订单金额与收入披露。",
        "inflection_verdict": "PARTIAL_INFLECTION_MIXED_SCOPE",
        "r04_valuation_readiness": "READY_FOR_SCENARIO_VALUATION_WITH_LIMITS",
        "r04_scenario_constraints": "可用情景：按集团总量或工业机器人及自动化应用系统混合分部(H1 7.07亿)建情景，显式纳入板块毛利率波动；待证/禁入假设：H1纯本体金额UNKNOWN，严禁为小拓/星仔/矩阵智拓单独赋营收或估值溢价。",
    },
    "SZ:002747": {
        "r02_topic_id": "R02_T02",
        "product_line_separation": "已量产收入线：工业机器人及智能制造系统（FY25 39.97亿/+31.80%；2026H1 21.38亿/+2.21%，占82.96%，含Cloos及系统集成）与自动化核心部件（H1 4.39亿/-3.78%）；期后并表/早期线：埃斯顿酷卓（H1仅13.95%参股不并表，2026-09-08交割后100%并表，FY25亏5,300万，两代人形独立收入未披露/UNKNOWN）、鼎汇具身创新中心（54.17%并表，截至知识截止日独立产品收入未披露/UNKNOWN）。",
        "two_period_comparable_facts": "同报告期H1对比(2025H1 vs 2026H1)：2026H1总营收25.78亿(S02 M01同比+1.14%)，工业机器人及智能制造系统21.38亿(+2.21%)增速平缓，但毛利率显著修复（机器人板块31.69%/+4.69pp，核心部件32.40%/+1.82pp，合并M04=+4.17pp）；扣非净利由2025H1的-1,760万转正至+7,017万（直接披露，改善+8,777万），归母净利1.61亿。",
        "alternative_explanations": "①一次性非现金收益主导账面利润（RH06）：H1非经常性损益9,115万占归母净利56.5%，主因南京工艺置换南京化纤股权产生9,950万公允价值变动收益，且2025H1扣非为负基数；②现金流严重背离（RH04）：H1经营现金流仅4,453万(M08=0.276)，应收账款增2.95亿、合同负债降1.87亿，盈利尚未转化为真实现金；③营收端+2.21%远低于NBS工业机器人H1产量+28.0%，仅见毛利修复未见量增拐点。",
        "falsifiers": "F1：2026全年经营现金流/扣非净利仍低于0.5且应收账款增速持续高于营收增速；F2：酷卓2026Q4并表后亏损扩大拖累集团扣非净利重回下滑；F3：工业机器人及智能制造系统毛利率回落至30%以下且合同负债继续萎缩。",
        "evidence_gaps": "G1：工业机器人本体与智能制造系统、Cloos海外单体收入及盈利均未拆分；G2：酷卓2026年9月并表后的整合亏损与协作/人形分项收入尚未经合并报表验证。",
        "inflection_verdict": "CONDITIONAL_INFLECTION_QUALITY_WATCH",
        "r04_valuation_readiness": "HOLD_UNTIL_QUALITY_OR_SCOPE_CLARIFIED",
        "r04_scenario_constraints": "暂留HOLD（不优先入R04基准估值）：须先验证剔除9,950万公允价值收益后的扣非持续性、现金流修复及酷卓Q4并表损益；若强行纳入仅可作高不确定性压力情景。",
    },
    "SZ:002472": {
        "r02_topic_id": "R02_T01",
        "product_line_separation": "已量产混合收入线：“减速器及其他”（FY25 7.95亿/+21.18%；2026H1 4.40亿/+26.18%，占总营收9.67%，含环动科技61.29%并表RV减速器及非机器人减速器）；研发线：新型重载RV减速器、电机减速器一体化旋转关节模组（研发阶段，独立收入未披露/UNKNOWN）；非机器人主业：乘用车/商用车/工程机械齿轮及智能执行机构（占总营收超90%）。",
        "two_period_comparable_facts": "同口径对比：“减速器及其他”连续两期保持20%+稳健增长（FY25 7.95亿/+21.18%；2026H1 4.40亿/+26.18%，按同比复算2025H1约3.49亿），自算毛利率由FY25的38.47%升至2026H1的47.47%（均属混合大类口径）；集团2026H1经营现金流11.12亿(+13.38%，M08=1.89)保持优异。",
        "alternative_explanations": "①体量占比小且口径混合：“减速器及其他”仅占集团总营收9.67%且混含非机器人传动产品，无法将集团整体盈利改善归因于机器人拐点；②环动科技单体营收、净利润及RV出货量均未在母公司定期报告披露，47.47%自算毛利率无法单独验证归属RV；③科创板分拆近两年仍停在“尚在进行中”，且谐波减速器是否自产未披露。",
        "falsifiers": "F1：“减速器及其他”增速跌破15%或自算毛利率回落至40%以下；F2：环动科技分拆问询/披露显示RV减速器净利停滞或客户集中度恶化；F3：存货周转天数（H1约125.8天）持续拉长并伴随跌价计提大增。",
        "evidence_gaps": "G1：纯RV减速器收入与环动科技单体净利润均UNKNOWN；G2：机器人减速器在手订单与谐波减速器自产进度未披露。",
        "inflection_verdict": "PARTIAL_INFLECTION_MIXED_SCOPE",
        "r04_valuation_readiness": "READY_FOR_SCENARIO_VALUATION_WITH_LIMITS",
        "r04_scenario_constraints": "可用情景：按集团总量及“减速器及其他”混合分部(占比9.67%)建分部加总敏感性情景；待证/禁入假设：纯RV收入与环动单体净利UNKNOWN，严禁把4.40亿或47.47%毛利率等同于纯RV盈利。",
    },
    "SZ:002979": {
        "r02_topic_id": "R02_T01",
        "product_line_separation": "已量产混合收入线：伺服系统类（FY25 9.22亿/+30.03%；2026Q1-Q3 10.08亿/+58.64%，占9M营收52.81%，通用工控为主；“含未单列的无框力矩电机等机器人核心部件”属按产品对应关系的合理推断，非原文直接表述，承接R01限制）；小批量/订单线：无框力矩电机（FY25交付超12万台、H1在手订单超100万台单位数口径，独立收入未披露/UNKNOWN）、谐波/行星关节模组及灵巧手（获近百家客户订单，独立收入未披露/UNKNOWN）；非机器人线：步进系统、控制技术类。",
        "two_period_comparable_facts": "9M独立锚定（9M累计与Q3单季分别对比各自2025年同期）：①9M累计(2025Q1-Q3 vs 2026Q1-Q3)：集团总营收19.09亿(直接披露，同比+46.77%，按同比复算2025Q1-Q3约13.00亿)、归母净利2.99亿(直接披露，同比+86.80%，复算2025Q1-Q3约1.60亿)、经营现金流-5,153万(直接披露，M08=-0.172；2025Q1-Q3同期经营现金流金额未在R00/R01已验收底稿单列，记UNKNOWN)；伺服系统类1-9月10.08亿(直接披露，同比+58.64%，复算2025Q1-Q3约6.35亿；R02_T01 9M主线集团营收中位增速+34.51%仅作背景参照)；②Q3单季(2025Q3 vs 2026Q3)：集团营收6.61亿(直接披露，同比+61.70%，复算2025Q3约4.09亿)、归母净利1.06亿(直接披露，同比+156.10%，复算2025Q3约0.41亿)、单季经营现金流-9,489万(直接披露；2025Q3同期单季经营现金流金额未在R00/R01已验收底稿单列，记UNKNOWN)；③H1分部补充(直接披露)：2026H1伺服系统类6.61亿 vs 2025H1 4.27亿(+54.82%，毛利率28.97%/+1.34pp)。",
        "alternative_explanations": "①现金流剧烈背离（RH04核心警报）：9M经营现金流转负至-5,153万(M08=-0.172)，Q3单季恶化至-9,489万，收现增速(+19.46%)远慢于收入(+46.77%)，票据+款项融资增2.81亿、存货增2.07亿(+49.75%)；②通用工控周期共振：伺服系统包含大量非机器人通用自动化设备，且机器人部件归入伺服属推断而非原文直列，不能把58.6%增速全归人形机器人；③“100万台在手订单”为单位数且无单价/交付期，严禁折算收入，在建300万台产能不等于盈利兑现。",
        "falsifiers": "F1：2026Q4经营现金流未能转正回补，全年经营现金流/归母净利仍低于0.5；F2：应收票据与存货继续高速扩张并引发大额减值或坏账；F3：2026年报仍不单列机器人部件收入，或伺服系统增速回落至20%以下。",
        "evidence_gaps": "G1：机器人核心部件收入金额与毛利率均未单列（三季报无分部表），且归入伺服系统类属推断；G2：上海雷赛机器人/灵巧驱控/东莞雷赛三家机器人子公司单体收入与利润未直接披露；G3：2025Q1-Q3及2025Q3同期经营现金流金额未在R00/R01已验收底稿单列（记UNKNOWN），现金流同比变动幅度的精确基期值待后续补核。",
        "inflection_verdict": "CONDITIONAL_INFLECTION_QUALITY_WATCH",
        "r04_valuation_readiness": "READY_FOR_SCENARIO_VALUATION_WITH_LIMITS",
        "r04_scenario_constraints": "RH04已触发(9M及Q3单季现金流为负)下的强制边界：①可用情景仅限集团总量(9M 19.09亿)或伺服系统混合分部(9M 10.08亿)盈利与营运资金敏感性区间，且基准/悲观情景必须显式扣减票据与存货占款对自由现金流的压制；②待证/禁入假设：在2026Q4现金流转正回补(全年M08>=0.5)及年报单列机器人部件收入/毛利前，严禁设定纯机器人独立营收基数、严禁用“100万台订单”折算收入、严禁假设高现金转化率(如OCF/净利>=1.0)。",
    },
    "SH:688003": {
        "r02_topic_id": "R02_T01",
        "product_line_separation": "已量产混合收入线：具身大脑方案（FY25 1.78亿/+75.02%、毛利率21.03%；2026H1 1.58亿/+141.60%、占H1营收17.77%，H1毛利率未披露/UNKNOWN，混含商用车L4域控与机器人大脑域控；9M未拆）；非机器人主业：AI量检测装备（H1 3.75亿/42.24%）、AI制程装备（H1 3.55亿/39.99%）；参股不并表：苏州矽行半导体（H1亏6,256万）。",
        "two_period_comparable_facts": "9M独立锚定（集团总量，2025同期 vs 2026同期）：①9M累计(2025Q1-Q3 vs 2026Q1-Q3)：集团营收14.86亿(直接披露，同比+52.07%，按同比复算2025Q1-Q3约9.77亿)，归母净利6,646万、扣非净利2,147万(直接披露；2025Q1-Q3同期归母与扣非具体金额未在R00/R01已验收底稿单列，记UNKNOWN，三季报同比标“不适用”且S02 M05记UNDEFINED_BASE)，9M经营现金流9,699万(直接披露同比+209.89%，复算2025Q1-Q3约3,130万)；②Q3单季(2025Q3 vs 2026Q3)：集团营收5.98亿(直接披露，同比+57.46%，复算2025Q3约3.80亿)，归母净利-3,203万、扣非净利+1,113万(直接披露；2025Q3同期归母与扣非具体金额未在R00/R01已验收底稿单列，记UNKNOWN，三季报同比标“不适用”且S02 M07记UNDEFINED_BASE)；③H1分部与订单另列(2025H1 vs 2026H1，9M未披露)：2026H1具身大脑方案营收1.58亿(直接披露，同比+141.60%，复算2025H1约0.65亿；H1毛利率UNKNOWN)，同页具身大脑混合新签订单3.15亿(直接披露，同比+229.74%，复算2025H1约0.96亿)。",
        "alternative_explanations": "①非经常性损益剧烈扰动（RH06）：9M归母净利6,646万中扣非仅2,147万(占32.31%)，非经常性占67.69%；Q3单季归母亏3,203万系金融资产公允价值浮亏-4,489万（主业扣非+1,113万）；②存货暴增与子公司烧钱（RH02）：9M存货20.83亿(较年初+75.01%，原因未披露，历史周转率仅1.02)，核心具身子公司天准星智H1经营现金流-1.05亿、净利率仅4.1%；③具身方案混含无人物流车/Robotaxi/重卡L4域控且3C/PCB主业同步高增，纯人形机器人盈利贡献不可验证。",
        "falsifiers": "F1：2026年报存货继续扩张且存货周转率跌破1.0并计提大额跌价准备；F2：天准星智全年经营现金流持续大额为负或净利率转负；F3：2026年报披露具身大脑方案毛利率低于20%（注：FY25为21.03%，2026H1毛利率未披露/UNKNOWN）或混合新签订单同比增速回落至50%以下。",
        "evidence_gaps": "G1：纯人形机器人域控与商用车L4域控的收入及3.15亿新签订单均未拆分；G2：9M存货暴增75%的构成原因与具身大脑2026H1毛利率均未披露；G3：2025Q1-Q3及2025Q3同期归母净利与扣非净利具体金额未在R00/R01已验收底稿单列（记UNKNOWN，S02 M05/M07为UNDEFINED_BASE），利润改善绝对额待后续补核。",
        "inflection_verdict": "CONDITIONAL_INFLECTION_QUALITY_WATCH",
        "r04_valuation_readiness": "HOLD_UNTIL_QUALITY_OR_SCOPE_CLARIFIED",
        "r04_scenario_constraints": "暂留HOLD（不优先入R04基准估值）：须先澄清9M存货暴增75%成因、天准星智现金流(-1.05亿)与纯人形/商用车L4域控拆分；若强行纳入仅可作高不确定性压力情景。",
    },
    "BJ:920593": {
        "r02_topic_id": "R02_T01",
        "product_line_separation": "已量产混合收入线：直流电机及组件（FY25 4,228万/+118.39%；2026H1 4,024万/+202.29%，占20.50%，含机器人减速电机+驱控一体化批量供货及工业设备项目，未单列纯机器人金额）；研究阶段线：无框电机、空心杯电机、关节模组、伺服电缸、人形用高精度丝杠（年报p27全部标注“研究阶段”，独立收入未披露/UNKNOWN）；非机器人/并表线：线性执行器(医疗/工控为主，38.85%)、赛仑特传动部件(2025-12起并表，H1 3,696万，未披露机器人用途)；5家参股公司(含中科灵犀5%)不并表。",
        "two_period_comparable_facts": "同口径对比：直流电机及组件连续两期翻倍以上增长（FY25 4,228万/+118.39%；2026H1 4,024万/+202.29%，按同比复算2025H1约1,331万）；2026H1经营现金流5,099万(+313.66%，M08=2.87)、合同负债2,570万(+330.86%)互相印证；美国鼎智(100%)海外机器人项目实现批量生产。",
        "alternative_explanations": "①并表增厚营收：2026H1总营收+58.92%（增7,278万）中，赛仑特2025年12月起并表即贡献4,721万（占比超六成），剔除并表后的内生增速远低于表观；②结构性毛利下滑与利润承压：低毛利直流电机(30.43%)与传动部件(39.94%)占比上升拉低综合毛利率6.31pp至45.91%，H1归母净利同比-11.61%（扣股份支付后+27.69%）；③两期自述存货周转时间变长（存货+35.25%、周转率1.30），且年报正文“单项+687.23%”与附注“减速电机及驱控+127.72%”口径冲突。",
        "falsifiers": "F1：赛仑特并表满周年后（2026Q4/2027H1）集团内生营收增速回落至15%以下；F2：直流电机及组件毛利率跌破28%或存货跌价计提大幅上升；F3：合同负债大幅回落且无框/空心杯/人形丝杠长期停留在研究阶段无量产订单。",
        "evidence_gaps": "G1：2026H1不再拆“减速电机及驱控”子行，纯机器人收入及美国鼎智机器人占比均UNKNOWN；G2：H1存货分类账面余额与库龄未在文本层披露，且冻结S02 M04(+15.22pp)与半年报综合毛利率(-6.31pp)基期口径差异待专项复核。",
        "inflection_verdict": "PARTIAL_INFLECTION_MIXED_SCOPE",
        "r04_valuation_readiness": "READY_FOR_SCENARIO_VALUATION_WITH_LIMITS",
        "r04_scenario_constraints": "可用情景：按剔除赛仑特并表效应后的集团内生增速与直流电机混合分部建情景，显式反映综合毛利率下行压力；待证/禁入假设：研究阶段的无框/空心杯/人形丝杠及纯机器人金额UNKNOWN，严禁单列营收假设。",
    },
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_lf_bytes(p: pathlib.Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def write_lf_text(p: pathlib.Path, s: str) -> bytes:
    b = s.replace("\r\n", "\n").encode("utf-8")
    p.write_bytes(b)
    return b


def write_lf_csv(p: pathlib.Path, cols: list, rows: list) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    b = buf.getvalue().encode("utf-8")
    p.write_bytes(b)
    return b


def main() -> int:
    R03_DIR.mkdir(parents=True, exist_ok=True)
    rel = json.loads((ROOT / "runs/issues/R03/release_20261127.json").read_text(encoding="utf-8"))
    r01_attr = json.loads((ROOT / "runs/issues/R01/attribution_review.json").read_text(encoding="utf-8"))
    r01_by_sid = {c["security_id"]: c for c in r01_attr["companies"]}

    # Load R02 industry signals dynamically
    r02_l1 = {}
    r02_l2 = {}
    with (ROOT / "runs/issues/R02/industry_signals.csv").open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if "LAYER_1" in row["signal_layer"]:
                r02_l1[row["signal_id"]] = row
            elif "LAYER_2" in row["signal_layer"] and row["denominator"] == "R00_MAINLINE":
                r02_l2[(row["topic_id"], row["period_key"], row["metric_id"])] = row

    def build_r02_ref(topic_id: str, anchor: str) -> str:
        m01 = r02_l2[(topic_id, anchor, "M01")]
        m04 = r02_l2[(topic_id, anchor, "M04")]
        m05 = r02_l2[(topic_id, anchor, "M05")]
        if anchor == "20260630":
            ind = r02_l1["L1:ROBOT_INDUSTRIAL_OUTPUT_CUM:2026H1"]
            ind_m = r02_l1["L1:ROBOT_INDUSTRIAL_OUTPUT_M:202606"]
            return (
                f"NBS工业机器人2026H1累计{ind['value']}套(+{ind['yoy_pct']}%)、6月单月+{ind_m['yoy_pct']}%；"
                f"池内{topic_id}(H1主线)营收改善{m01['improved_share_pct']}%({m01['improved_count']}/{m01['valid_paired_count']}，有效配对覆盖{m01['valid_paired_count']}/{m01['denominator_count']}，中位+{float(m01['median_value'])*100:.2f}%)、"
                f"毛利改善{m04['improved_share_pct']}%({m04['improved_count']}/{m04['valid_paired_count']})、"
                f"扣非改善{m05['improved_share_pct']}%({m05['improved_count']}/{m05['valid_paired_count']}，有效配对覆盖{m05['valid_paired_count']}/{m05['denominator_count']})。"
                f"【口径边界：行业产量与池内景气!=单公司机器人收入】"
            )
        ind = r02_l1["L1:ROBOT_INDUSTRIAL_OUTPUT_CUM:2026Q1Q3"]
        ind_m = r02_l1["L1:ROBOT_INDUSTRIAL_OUTPUT_M:202609"]
        svc_m = r02_l1["L1:ROBOT_SERVICE_OUTPUT_M:202609"]
        return (
            f"NBS工业机器人2026Q1-Q3累计{ind['value']}套(+{ind['yoy_pct']}%)、9月单月回落至+{ind_m['yoy_pct']}%（服务机器人9月单月{svc_m['yoy_pct']}%）；"
            f"池内{topic_id}(9M主线)营收改善{m01['improved_share_pct']}%({m01['improved_count']}/{m01['valid_paired_count']}，有效配对覆盖{m01['valid_paired_count']}/{m01['denominator_count']}，中位+{float(m01['median_value'])*100:.2f}%)、"
            f"毛利改善{m04['improved_share_pct']}%({m04['improved_count']}/{m04['valid_paired_count']})、"
            f"扣非改善{m05['improved_share_pct']}%({m05['improved_count']}/{m05['valid_paired_count']}，有效配对覆盖{m05['valid_paired_count']}/{m05['denominator_count']})。"
            f"【口径边界：9M样本较小且行业景气!=单公司机器人收入】"
        )

    dispatch_rows = []
    case_rows = []
    for ci in rel["child_issues"]:
        bid = ci["batch_id"]
        inum = ci["issue_number"]
        for sid in ci["companies"]:
            r1 = r01_by_sid[sid]
            c = CASES[sid]
            ap = r1["anchor_period"]
            dispatch_rows.append({
                "batch_id": bid,
                "child_issue_number": str(inum),
                "security_id": sid,
                "stock_name": r1["stock_name"],
                "anchor_period": ap,
                "anchor_group": "H1_20260630" if ap == "20260630" else "9M_20260930",
                "r02_topic_id": c["r02_topic_id"],
                "r01_priority_bucket": r1["r03_priority_bucket"],
                "s05_rh_triggers": r1["financial_metrics_from_s02_s05"]["s05_rh_triggers"],
                "s05_pending_flags": r1["financial_metrics_from_s02_s05"]["s05_pending_flags"],
                "dispatch_status": "INFLECTION_EVALUATED_SELF_CHECK",
            })
            case_rows.append({
                "security_id": sid,
                "stock_name": r1["stock_name"],
                "batch_id": bid,
                "child_issue_number": str(inum),
                "anchor_period": ap,
                "knowledge_as_of": KNOWLEDGE_AS_OF,
                "r02_topic_id": c["r02_topic_id"],
                "r02_industry_signal_ref": build_r02_ref(c["r02_topic_id"], ap),
                "product_line_separation": c["product_line_separation"],
                "two_period_comparable_facts": c["two_period_comparable_facts"],
                "alternative_explanations": c["alternative_explanations"],
                "falsifiers": c["falsifiers"],
                "evidence_gaps": c["evidence_gaps"],
                "inflection_verdict": c["inflection_verdict"],
                "r04_valuation_readiness": c["r04_valuation_readiness"],
                "r04_scenario_constraints": c["r04_scenario_constraints"],
            })

    write_lf_csv(R03_DIR / "inflection_batch_dispatch.csv", list(dispatch_rows[0].keys()), dispatch_rows)
    write_lf_csv(R03_DIR / "inflection_cases.csv", list(case_rows[0].keys()), case_rows)

    # counter_evidence.md
    ce = [
        "# R03（#47）行业与公司拐点反方证据、替代解释与可推翻信号汇编",
        "",
        f"- 计划版本：`20261026_collection_first_v2`；知识截止日：`{KNOWLEDGE_AS_OF}`；固定时间：`{FIXED_NOW}`",
        "- 覆盖范围：`#63 R03_BATCH_01`（拓斯达、埃斯顿、双环传动，3×H1）与 `#64 R03_BATCH_02`（雷赛智能、天准科技、鼎智科技，2×9M + 1×H1），严格分期、禁止跨期合并。",
        "- **总原则**：严禁先写乐观结论再找证据；不把行业产量当公司收入、不把样机/合作/计划产能当盈利兑现、不取最高阶段代表整家公司。",
        "",
        "## 一、行业层反方证据（来自已验收 R02 #46）",
        "1. **工业机器人累计抬升但单月边际回落**：NBS 工业机器人 2026Q1-Q3 累计产量 794,781 套（+29.1%），高于 H1（+28.0%），但 9 月单月增速由 6 月的 +28.1% 回落至 +18.9%，边际动能需跟踪。",
        "2. **服务机器人单月显著转负**：服务机器人 1-9 月累计 +7.9%，但 9 月单月 1,658,178 套、同比 **-17.8%**，存在明显背离，不可只引累计值。",
        "3. **价格与口径边界**：PPI 由负转正（2025-12 -1.9% -> 2026-09 +5.0%）不等于机器人企业实际售价上涨；国民经济行业无独立“机器人制造业”增加值（`NBS_ROBOT_INDUSTRY_VA=UNKNOWN`）；9M 锚定样本量显著小于 H1，改善占比存在抽样波动。",
        "",
        "## 二、逐家反方证据、替代解释与可推翻信号（6 家核心公司）",
        "",
    ]
    for r in case_rows:
        ce += [
            f"### {r['security_id']} {r['stock_name']}（`{r['batch_id']}` / #{r['child_issue_number']} / 锚定 `{r['anchor_period']}`）",
            f"- **拐点判定**：`{r['inflection_verdict']}` ｜ **R04 估值准入建议**：`{r['r04_valuation_readiness']}`",
            f"- **R04 情景估值约束边界**：{r['r04_scenario_constraints']}",
            f"- **产品线严格分层**：{r['product_line_separation']}",
            f"- **两期可比事实**：{r['two_period_comparable_facts']}",
            f"- **反方替代解释（为何可能不是真拐点）**：{r['alternative_explanations']}",
            f"- **未来可推翻信号（Falsifiers）**：{r['falsifiers']}",
            f"- **当前缺证条件（Evidence Gaps）**：{r['evidence_gaps']}",
            "",
        ]
    write_lf_text(R03_DIR / "counter_evidence.md", "\n".join(ce) + "\n")

    # handoff.md
    ready_r04 = [f"{r['security_id']} {r['stock_name']}" for r in case_rows if r["r04_valuation_readiness"] == "READY_FOR_SCENARIO_VALUATION_WITH_LIMITS"]
    hold_r04 = [f"{r['security_id']} {r['stock_name']}" for r in case_rows if r["r04_valuation_readiness"] != "READY_FOR_SCENARIO_VALUATION_WITH_LIMITS"]
    ho = [
        "# R03（#47）公司与行业拐点研究交接说明（#63 Batch 01 + #64 Batch 02 共 6 家）",
        "",
        f"- 计划版本：`20261026_collection_first_v2`；知识截止日：`{KNOWLEDGE_AS_OF}`；固定重跑时间：`{FIXED_NOW}`",
        "- 复核性质：`SELF_CHECK`（待 Codex 干净树独立复核）；`R04_released=false`、`#53 OPEN` 未触碰。",
        "",
        "## 1. 复现命令",
        "```powershell",
        f"$env:R03_FIXED_NOW='{FIXED_NOW}'; py runs/issues/R03/step_r03_build.py; py runs/issues/R03/step_r03_verify.py",
        "```",
        "",
        "## 2. 6 家核心公司拐点研判与 R04 准入分层（仅研究排包，非投资建议）",
        "",
        "| 批次 | 代码 | 名称 | 锚定期 | 拐点判定 | R04 情景估值准入建议 | R04 强制边界摘要 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in case_rows:
        ho.append(f"| `{r['batch_id']}` | `{r['security_id']}` | {r['stock_name']} | `{r['anchor_period']}` | `{r['inflection_verdict']}` | `{r['r04_valuation_readiness']}` | {r['r04_scenario_constraints']} |")
    ho += [
        "",
        f"- **可带限制进入 R04 情景估值（4 家）**：{', '.join(ready_r04)}（其中雷赛智能因 RH04 已触发且 9M/Q3 单季经营现金流为负，仅允许集团总量/伺服混合分部盈利及营运资金敏感性情景，严禁设定纯机器人独立营收基数、用“100万台订单”折算收入或直接假设高现金转化率）",
        f"- **暂留质量/口径观察（2 家，需先验证现金流/扣非/存货或按高不确定性处理）**：{', '.join(hold_r04)}",
        "",
        "## 3. 结转至 R04 的铁律",
        "- 6 家公司在各自锚定期纯机器人本体收入均为 `UNKNOWN`，R04 严禁编造单一纯本体营收基数，必须按分部混合口径做情景与敏感性区间，且不输出买卖建议或目标价预测。",
    ]
    write_lf_text(R03_DIR / "handoff.md", "\n".join(ho) + "\n")

    # Dynamic checks
    anomalies = []
    checks = []

    def add_check(cid, name, ok, detail):
        checks.append({"id": cid, "name": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            anomalies.append(f"{cid}: {detail}")

    b1 = set(rel["child_issues"][0]["companies"])
    b2 = set(rel["child_issues"][1]["companies"])
    r01_pa = {c["security_id"] for c in r01_attr["companies"] if c["r03_priority_bucket"] == "R03_PRIORITY_A"}
    add_check("C01", "两批 3+3 家互斥零重复，100% 等于 R01 R03_PRIORITY_A 6 家",
              len(b1) == 3 and len(b2) == 3 and len(b1 & b2) == 0 and (b1 | b2) == r01_pa,
              f"b1={len(b1)} b2={len(b2)} overlap={len(b1&b2)}")
    add_check("C02", "4×H1 与 2×9M 锚定期严格分离并与 R01 一致",
              sum(1 for r in case_rows if r["anchor_period"] == "20260630") == 4
              and sum(1 for r in case_rows if r["anchor_period"] == "20260930") == 2
              and all(r["anchor_period"] == r01_by_sid[r["security_id"]]["anchor_period"] for r in case_rows),
              "h1=4 m9=2")
    add_check("C03", "6 家均具备产品线分层、两期可比事实、替代解释、可推翻信号与缺证条件",
              all(all(r[k].strip() for k in ("product_line_separation", "two_period_comparable_facts", "alternative_explanations", "falsifiers", "evidence_gaps")) for r in case_rows),
              "all_6_complete")
    add_check("C04", "6 家均已动态挂接同锚定期 R02 行业信号且保留口径边界",
              all("口径边界" in r["r02_industry_signal_ref"] for r in case_rows),
              "r02_signals_linked")
    add_check("C05", "全部 8 份输入存在且位于 Git 工作树内",
              all((ROOT / p).exists() for p in INPUT_PATHS),
              f"inputs={len(INPUT_PATHS)}")

    # manifest.json
    in_entries = []
    for rel_p in INPUT_PATHS:
        b = read_lf_bytes(ROOT / rel_p)
        in_entries.append({"path": rel_p, "bytes": len(b), "sha256": sha256_bytes(b)})

    deliv_paths = [
        "runs/issues/R03/inflection_batch_dispatch.csv",
        "runs/issues/R03/inflection_cases.csv",
        "runs/issues/R03/counter_evidence.md",
        "runs/issues/R03/handoff.md",
        "runs/issues/R03/step_r03_build.py",
    ]
    if (R03_DIR / "step_r03_verify.py").exists():
        deliv_paths.append("runs/issues/R03/step_r03_verify.py")

    deliv_entries = []
    for rel_p in sorted(deliv_paths):
        b = (ROOT / rel_p).read_bytes()
        deliv_entries.append({"path": rel_p, "bytes": len(b), "sha256": sha256_bytes(b)})

    root_digest = sha256_bytes("\n".join(f"{d['path']}:{d['sha256']}" for d in deliv_entries).encode("utf-8"))
    manifest = {
        "artifact": "R03_DELIVERY_MANIFEST",
        "issue_key": "R03",
        "issue_number": 47,
        "child_issues": [63, 64],
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "fixed_now": FIXED_NOW,
        "review_nature": "SELF_CHECK",
        "manifest_root_digest": root_digest,
        "input_count": len(in_entries),
        "deliverable_count": len(deliv_entries),
        "inputs": in_entries,
        "deliverables": deliv_entries,
        "anomaly_count": len(anomalies),
    }
    write_lf_text(R03_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    decision = "SELF_CHECK_PASS_WITH_LIMITS" if len(anomalies) == 0 else "NOT_ACCEPTED_PENDING_FIX"
    review = {
        "artifact": "R03_SELF_CHECK_REVIEW",
        "issue_key": "R03",
        "issue_number": 47,
        "child_issues": [63, 64],
        "plan_version": "20261026_collection_first_v2",
        "reviewed_on": "2026-11-28",
        "review_nature": "SELF_CHECK",
        "decision": decision,
        "anomalies": anomalies,
        "checks_summary": f"{sum(1 for c in checks if c['result']=='PASS')}/{len(checks)} PASS",
        "checks": checks,
        "counts": {
            "companies": len(case_rows),
            "h1_anchor": 4,
            "m9_anchor": 2,
            "ready_for_r04_with_limits": len(ready_r04),
            "hold_quality_or_scope": len(hold_r04),
        },
        "R04_released": False,
        "issue_53_touched": False,
        "issue_53_status": "OPEN",
        "review_provenance_refs": [],
    }
    write_lf_text(R03_DIR / "review.json", json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    print(f"R03 build done @ {FIXED_NOW} | companies={len(case_rows)} | checks={review['checks_summary']} | decision={decision}")
    print(f"manifest_root_digest={root_digest}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
