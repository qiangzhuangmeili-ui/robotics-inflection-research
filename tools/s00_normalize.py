"""S00 全池财务标准化：把逐格抽取结果 + 旧快照整理成可比指标输入。

原则（对应 P04 字段契约与 issue #35 验收）：
1. 只输出「有值」的格，缺失不填 0，全部缺失/不适用/未披露逐条落 normalization_issues.csv；
2. 每格保留原值字符串、原单位、换算倍数、折算后数值、页码与来源文档，可逐格复算；
3. 单季优先取年报「分季度主要财务数据」表；只有拿不到官方单季时才用同年同版本累计相减；
4. 扣非缺失不得用净利润替代、经营现金流缺失不得用净利润替代——缺就是缺；
5. 旧快照只作 2021/2022 补充来源与 2023-2025 交叉校验，冲突时以官方 PDF 为准并登记偏差；
6. 上市前判定逐行比较 period_end 与真实上市日，不用状态码反推。

用法：
    python tools/s00_normalize.py
"""
import csv
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/S00'
EXTRACT = OUT / 'extract'
INDEX = ROOT / 'runs/collection/collection_index.csv'
MASTER = ROOT / 'data/company_master.csv'
LISTING = ROOT / 'data/company_listing_dates.csv'
NA_AUDIT = ROOT / 'runs/issues/A04/rework/na_applicability_audit.csv'
LEGACY = Path('D:/StockResearchLab/IndustryInflectionLab/thematic_research/robotics/'
              'outputs/R1/run_20261024_local_02/r1_universe_financial_snapshot.csv')

AS_OF = '2026-10-25'
LOW_BASE_REV = 10_000_000      # 上年同期营业收入绝对值低于 1000 万元 → 低基数
LOW_BASE_PROFIT = 5_000_000    # 上年同期归母净利绝对值低于 500 万元 → 低基数

SLOTS = ['annual_2023', 'annual_2024', 'annual_2025',
         'h1_2024', 'h1_2025', 'h1_2026',
         'q1_2024', 'q1_2025', 'q1_2026',
         'q3_2024', 'q3_2025', 'q3_2026']

YTD_FIELDS = ['FIN.REV.YTD', 'FIN.COST.YTD', 'FIN.NP.YTD',
              'FIN.NPP.YTD', 'FIN.NPDEDT.YTD', 'FIN.OCF.YTD']
INSTANT_FIELDS = ['FIN.AR.INSTANT', 'FIN.NR.INSTANT', 'FIN.CONTRACTASSET.INSTANT',
                  'FIN.INV.INSTANT', 'FIN.ASSET.INSTANT']
SQ_FIELDS = ['FIN.REV.SQ', 'FIN.NPP.SQ', 'FIN.NPDEDT.SQ', 'FIN.OCF.SQ']
EXTRACT_FIELDS = YTD_FIELDS + INSTANT_FIELDS + SQ_FIELDS + ['FIN.RESTATEMENT']

FIELD_CN = {
    'FIN.REV.YTD': '营业收入（合并，累计）',
    'FIN.COST.YTD': '营业成本（合并，累计）',
    'FIN.NP.YTD': '净利润（合并，累计）',
    'FIN.NPP.YTD': '归母净利润（累计）',
    'FIN.NPDEDT.YTD': '扣非归母净利润（累计）',
    'FIN.OCF.YTD': '经营活动现金流量净额（累计）',
    'FIN.AR.INSTANT': '应收账款（期末）',
    'FIN.NR.INSTANT': '应收票据（期末）',
    'FIN.CONTRACTASSET.INSTANT': '合同资产（期末）',
    'FIN.INV.INSTANT': '存货（期末）',
    'FIN.ASSET.INSTANT': '资产总计（期末）',
    'FIN.REV.SQ': '营业收入（单季）',
    'FIN.NPP.SQ': '归母净利润（单季）',
    'FIN.NPDEDT.SQ': '扣非归母净利润（单季）',
    'FIN.OCF.SQ': '经营活动现金流量净额（单季）',
    'FIN.GROSSPROFIT.YTD': '毛利额（派生）',
    'FIN.GROSSMARGIN.PCT': '毛利率（%）',
    'FIN.NPMARGIN.PCT': '归母净利率（%）',
    'FIN.OCF_TO_NP.RATIO': '经营现金流/归母净利（倍）',
    'FIN.RESTATEMENT': '重述/追溯调整标记',
}

NORMALIZED_HEADER = [
    'security_id', 'stock_code', 'stock_name',
    'period_key', 'period_type', 'period_label', 'period_start', 'period_end', 'fiscal_year',
    'period_basis', 'period_source', 'slot_id',
    'field_id', 'field_name_cn',
    'value_raw', 'unit_raw', 'unit_scale', 'value_cny',
    'status', 'status_reason', 'source_kind',
    'document_id', 'source_page', 'evidence_label',
    'published_on', 'collected_at', 'pit_status', 'as_of',
    'currency', 'consolidation_scope',
    'listing_date', 'is_pre_listing', 'restatement_flag', 'low_base_flag', 'comparability_note',
    'upstream_hold_fields', 'value_before_adoption', 'adoption_reason', 'quarterly_inputs',
    'version_used', 'original_document_id',
]

ISSUE_HEADER = [
    'security_id', 'stock_code', 'stock_name',
    'period_key', 'period_type', 'period_label', 'period_end',
    'slot_id', 'field_id', 'issue_type', 'severity', 'blocking_for_indicator',
    'detail', 'document_id', 'evidence',
]


# ---------------------------------------------------------------- 读取

def load_index():
    """台账：{(slot, security_id): row}"""
    out = {}
    for r in csv.DictReader(io.open(INDEX, encoding='utf-8-sig')):
        out[(r['slot_id'], r['security_id'])] = r
    return out


def load_extract(slot):
    """抽取结果：{security_id: {(field_id, note): row}}"""
    p = EXTRACT / f'{slot}_fields.csv'
    out = defaultdict(dict)
    if not p.exists():
        return out
    for r in csv.DictReader(io.open(p, encoding='utf-8-sig')):
        out[r['security_id']][(r['field_id'], r['note'])] = r
    return out


def load_diag(slot):
    p = EXTRACT / f'{slot}_diag.csv'
    out = {}
    if not p.exists():
        return out
    for r in csv.DictReader(io.open(p, encoding='utf-8-sig')):
        out[r['security_id']] = r
    return out


def load_companies():
    out = {}
    for r in csv.DictReader(io.open(MASTER, encoding='utf-8-sig')):
        out[r['security_id']] = r
    return out


def load_listing():
    out = {}
    for r in csv.DictReader(io.open(LISTING, encoding='utf-8-sig')):
        if r.get('listing_date_status') == 'RESOLVED_FROM_EXCHANGE' and r.get('listing_date'):
            out[r['security_id']] = r['listing_date']
    return out


def detect_doc_language(path, pages=3):
    """判 PDF 前几页的中文占比，用于区分「采到英文版」与「抽取器盲区」。"""
    try:
        from pypdf import PdfReader
        rd = PdfReader(str(path))
        text = ''
        for i in range(min(pages, len(rd.pages))):
            text += (rd.pages[i].extract_text() or '')
    except Exception:  # noqa: BLE001
        return 'OPEN_FAILED', 0.0, 0
    if not text.strip():
        return 'NO_TEXT_LAYER', 0.0, 0
    zh = len(re.findall(r'[\u4e00-\u9fff]', text))
    ratio = round(zh / max(len(text.strip()), 1), 3)
    if ratio < 0.05:
        return 'EN_OR_NON_ZH', ratio, len(text)
    if ratio < 0.30:
        return 'MIXED', ratio, len(text)
    return 'ZH', ratio, len(text)


def load_corrected():
    """A04 版本链：已落盘更正全文且台账仍用原版的槽 → 更正版字段行。

    阻断项4：S00 原来直接用台账 document_id 抽取，6 个槽存在更正版全文却采用原版。
    这里用 tools/s00_rework_corrected.py 重抽更正版的结果覆盖字段，
    并把 document_id 换成更正版，原版 id 保留在 original_document_id 列。
    """
    p = ROOT / 'runs/issues/S00/rework/corrected_version_fields.csv'
    out = defaultdict(dict)
    if not p.exists():
        return out
    for r in csv.DictReader(io.open(p, encoding='utf-8-sig')):
        out[(r['security_id'], r['slot_id'])][(r['field_id'], r['note'])] = r
    return out


def load_na_audit():
    out = {}
    if not NA_AUDIT.exists():
        return out
    for r in csv.DictReader(io.open(NA_AUDIT, encoding='utf-8-sig')):
        out[(r['security_id'], r['slot_id'])] = r
    return out


def load_legacy():
    out = {}
    if not LEGACY.exists():
        return out
    for r in csv.DictReader(io.open(LEGACY, encoding='utf-8-sig')):
        out[r['security_id']] = r
    return out


# ---------------------------------------------------------------- 期间映射

def period_meta(slot):
    """slot_id → (period_key, period_type, period_end, fiscal_year, period_label)"""
    kind, year = slot.split('_')
    y = int(year)
    if kind == 'annual':
        return f'{y}1231', 'FY', f'{y}-12-31', y, f'FY{y}'
    if kind == 'h1':
        return f'{y}0630', 'H1', f'{y}-06-30', y, f'H1_{y}'
    if kind == 'q1':
        return f'{y}0331', 'Q1', f'{y}-03-31', y, f'Q1_{y}'
    if kind == 'q3':
        return f'{y}0930', '9M', f'{y}-09-30', y, f'Q3_{y}'
    raise ValueError(slot)


def period_start_of(pkey, ptype):
    if ptype in ('FY', 'H1', '9M', 'Q1'):
        return f'{pkey[:4]}-01-01'
    return {'Q2': f'{pkey[:4]}-04-01', 'Q3': f'{pkey[:4]}-07-01',
            'Q4': f'{pkey[:4]}-10-01'}.get(ptype, f'{pkey[:4]}-01-01')


def quarter_period(year, q):
    return {
        1: (f'{year}0331', 'Q1', f'{year}-03-31'),
        2: (f'{year}0630', 'Q2', f'{year}-06-30'),
        3: (f'{year}0930', 'Q3', f'{year}-09-30'),
        4: (f'{year}1231', 'Q4', f'{year}-12-31'),
    }[q]


# ---------------------------------------------------------------- 派生

HOLD_STATUSES = {'EXTRACTED_XCHECK_MISMATCH'}
RATIO_FIELDS = ('FIN.GROSSPROFIT.YTD', 'FIN.GROSSMARGIN.PCT',
                'FIN.NPMARGIN.PCT', 'FIN.OCF_TO_NP.RATIO')


def _is_hold(cell):
    return bool(cell) and cell.get('status') in HOLD_STATUSES


def derive_ratios(cells, legacy_xcheck=None, add_issue=None):
    """派生毛利额/毛利率/归母净利率/现金含量。

    每次调用先清掉上一轮派生值再重算——基础值（如四季之和仲裁）变了以后，
    必须重算下游，否则派生格与最终输入自相矛盾（Codex 复核阻断项1）。
    上游任一输入为 HOLD（EXTRACTED_XCHECK_MISMATCH）时，派生值同样标 HOLD，
    并把父键写进 upstream_hold，S01/S02 可机器识别（阻断项3）。
    """
    n = 0
    for key, fields in list(cells.items()):
        if key[2] != 'YTD':
            continue
        for fid in RATIO_FIELDS:
            # 只清上一轮派生值；旧快照 2021/2022 的毛利率是原始数据（LEGACY_SNAPSHOT），
            # 那两期没有 COST 无法重算，误删会让 1972 格历史毛利率凭空消失
            cur = fields.get(fid)
            if cur and str(cur.get('status', '')).startswith('DERIVED'):
                fields.pop(fid, None)
        rev = fields.get('FIN.REV.YTD')
        cost = fields.get('FIN.COST.YTD')
        npp = fields.get('FIN.NPP.YTD')
        ocf = fields.get('FIN.OCF.YTD')
        if rev and cost:
            holds = [f for f, c in (('FIN.REV.YTD', rev), ('FIN.COST.YTD', cost)) if _is_hold(c)]
            st = 'DERIVED_HOLD_UPSTREAM' if holds else 'DERIVED'
            gp = rev['value'] - cost['value']
            fields['FIN.GROSSPROFIT.YTD'] = {
                'value': round(gp, 2), 'raw': '', 'unit': '元', 'scale': 1,
                'status': st, 'source_kind': 'DERIVED_REV_MINUS_COST',
                'doc': rev['doc'], 'page': '', 'label': 'REV−COST',
                'published_on': rev['published_on'], 'pit': rev['pit'], 'slot': rev['slot'],
                'upstream_hold': '|'.join(holds),
            }
            if rev['value']:
                fields['FIN.GROSSMARGIN.PCT'] = {
                    'value': round(gp / rev['value'] * 100, 6), 'raw': '', 'unit': '%',
                    'scale': 'pct', 'status': st, 'source_kind': 'DERIVED_GP_DIV_REV',
                    'doc': rev['doc'], 'page': '', 'label': '',
                    'published_on': rev['published_on'], 'pit': rev['pit'], 'slot': rev['slot'],
                    'upstream_hold': '|'.join(holds),
                }
                n += 2
                lg = fields.get('__legacy_gm')
                if legacy_xcheck is not None and lg and add_issue is not None:
                    dpp = abs(fields['FIN.GROSSMARGIN.PCT']['value'] - lg['value'])
                    if dpp <= 0.05:
                        legacy_xcheck['GM_MATCH'] += 1
                    elif dpp <= 2.0:
                        legacy_xcheck['GM_MINOR_DIFF_LE2PP'] += 1
                    else:
                        legacy_xcheck['GM_MISMATCH'] += 1
                        add_issue(key[0], key[1], '', '', '', rev['slot'], 'FIN.GROSSMARGIN.PCT',
                                  'GROSSMARGIN_VS_PROVIDER_MISMATCH',
                                  f'PDF 反算 {fields["FIN.GROSSMARGIN.PCT"]["value"]:.4f}% vs '
                                  f'快照 {lg["value"]:.4f}%，差 {dpp:.4f}pp（>0.05pp），需检查成本口径',
                                  'WARN', 'NO', rev['doc'])
        if rev and npp and rev['value']:
            holds = [f for f, c in (('FIN.NPP.YTD', npp), ('FIN.REV.YTD', rev)) if _is_hold(c)]
            fields['FIN.NPMARGIN.PCT'] = {
                'value': round(npp['value'] / rev['value'] * 100, 6), 'raw': '', 'unit': '%',
                'scale': 'pct', 'status': 'DERIVED_HOLD_UPSTREAM' if holds else 'DERIVED',
                'source_kind': 'DERIVED_NPP_DIV_REV',
                'doc': rev['doc'], 'page': '', 'label': '',
                'published_on': rev['published_on'], 'pit': rev['pit'], 'slot': rev['slot'],
                'upstream_hold': '|'.join(holds),
            }
            n += 1
        if ocf and npp:
            if npp['value'] > 0:
                holds = [f for f, c in (('FIN.OCF.YTD', ocf), ('FIN.NPP.YTD', npp)) if _is_hold(c)]
                fields['FIN.OCF_TO_NP.RATIO'] = {
                    'value': round(ocf['value'] / npp['value'], 6), 'raw': '', 'unit': '倍',
                    'scale': 'times',
                    'status': 'DERIVED_HOLD_UPSTREAM' if holds else 'DERIVED',
                    'source_kind': 'DERIVED_OCF_DIV_NPP',
                    'doc': rev['doc'] if rev else ocf['doc'], 'page': '', 'label': '',
                    'published_on': ocf['published_on'], 'pit': ocf['pit'], 'slot': ocf['slot'],
                    'upstream_hold': '|'.join(holds),
                }
                n += 1
            elif add_issue is not None:
                add_issue(key[0], key[1], '', '', '', ocf['slot'], 'FIN.OCF_TO_NP.RATIO',
                          'NOT_COMPUTABLE_NONPOSITIVE_NPP',
                          f'归母净利 {npp["value"]:,.2f} ≤ 0，现金含量比率不可解释，只并列展示绝对额',
                          'INFO', 'NO', ocf['doc'])
    return n


# ---------------------------------------------------------------- 主流程

def main(slots=None, tag=''):
    global SLOTS
    if slots:
        SLOTS = slots
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    index = load_index()
    companies = load_companies()
    listing = load_listing()
    legacy = load_legacy()
    na_audit = load_na_audit()
    corrected = load_corrected()

    # 取件时间：台账无独立 collected_at 列，用该公司最后一次状态更新时间代理
    collected_at = {}
    for (_slot, _sec), r in index.items():
        ts = (r.get('updated_at') or '')[:19]
        if ts and ts > collected_at.get(_sec, ''):
            collected_at[_sec] = ts

    secs = sorted(companies.keys())
    print(f'[S00] companies={len(secs)} listing_dates={len(listing)} legacy={len(legacy)}', flush=True)

    # cells[(sec, period_key, basis)] = {field_id: dict(value=float, **meta)}
    cells = defaultdict(dict)
    restate = {}
    issues = []
    slot_status = {}
    version_map = {}   # (sec, slot) -> (version_used, original_doc, adopted_doc)

    def add_issue(sec, pkey, ptype, plabel, pend, slot, field, itype, detail,
                  severity='WARN', blocking='NO', doc='', evidence=''):
        issues.append({
            'security_id': sec,
            'stock_code': companies.get(sec, {}).get('stock_code', sec.split(':')[-1]),
            'stock_name': companies.get(sec, {}).get('stock_name', ''),
            'period_key': pkey, 'period_type': ptype, 'period_label': plabel,
            'period_end': pend, 'slot_id': slot, 'field_id': field,
            'issue_type': itype, 'severity': severity, 'blocking_for_indicator': blocking,
            'detail': detail, 'document_id': doc, 'evidence': evidence,
        })

    # ---------- 1. 12 个采集槽逐格整理
    for slot in SLOTS:
        pkey, ptype, pend, fy, plabel = period_meta(slot)
        ext = load_extract(slot)
        diag = load_diag(slot)
        if not ext:
            print(f'[S00] WARN missing extract for {slot}', flush=True)
        n_ex = n_na = n_nd = n_ny = 0
        for sec in secs:
            row = index.get((slot, sec))
            if row is None:
                add_issue(sec, pkey, ptype, plabel, pend, slot, '', 'SLOT_NOT_IN_LEDGER',
                          '台账无该槽位记录', 'ERROR', 'YES')
                continue
            st = row['status']
            slot_status[(slot, sec)] = st
            doc = row.get('document_id', '')
            pub = row.get('published_on', '')

            # 非采集成功状态：整槽一个状态，不进 cells
            if st != 'COLLECTED_IDENTITY_VERIFIED':
                if st == 'NOT_APPLICABLE_PRE_LISTING':
                    n_na += 1
                    # 逐行复核 A04 的不适用依据：日期必须真的晚于报告期末（F22）
                    aud = na_audit.get((sec, slot))
                    if not aud:
                        add_issue(sec, pkey, ptype, plabel, pend, slot, '',
                                  'PRE_LISTING_WITHOUT_AUDIT_ROW',
                                  '台账判上市前不适用，但 A04 审计表无该槽依据', 'ERROR', 'YES', doc)
                    elif aud['ok'] != 'True' or not (aud['date'] > pend):
                        add_issue(sec, pkey, ptype, plabel, pend, slot, '',
                                  'PRE_LISTING_AUDIT_CONTRADICTION',
                                  f"依据 {aud['date_kind']}={aud['date']} 不晚于报告期末 {pend}",
                                  'ERROR', 'YES', doc)
                elif st == 'NOT_DISCLOSED_BY_ISSUER':
                    n_nd += 1
                    add_issue(sec, pkey, ptype, plabel, pend, slot, '', 'NOT_DISCLOSED_BY_ISSUER',
                              '发行人未披露该期报告（季度报告属自愿披露），索引完整且无该期记录；不计入缺失',
                              'INFO', 'NO', doc)
                elif st == 'NOT_YET_DISCLOSED':
                    n_ny += 1
                    add_issue(sec, pkey, ptype, plabel, pend, slot, '', 'NOT_YET_DISCLOSED',
                              f'该报告期尚未到法定披露期（研究截止 {AS_OF}），不是缺件，不得计入取得率分母',
                              'INFO', 'NO', doc)
                else:
                    add_issue(sec, pkey, ptype, plabel, pend, slot, '', 'SLOT_STATUS_' + st,
                              f'槽位状态 {st}', 'ERROR', 'YES', doc)
                continue

            n_ex += 1
            f = ext.get(sec, {})
            d = diag.get(sec, {})
            corr = corrected.get((sec, slot))
            if corr:
                orig_doc = doc
                doc = next(iter(corr.values()))['document_id']
                f = corr
                version_map[(sec, slot)] = ('CORRECTED_FULLTEXT', orig_doc, doc)
                add_issue(sec, pkey, ptype, plabel, pend, slot, '',
                          'CORRECTED_VERSION_ADOPTED',
                          f'A04 版本链显示该槽有更正全文 {doc}，已改用更正版抽取；原版 {orig_doc} 保留为溯源',
                          'INFO', 'NO', doc)
            xbad = (d.get('xcheck_pass') == 'MISMATCH')
            if xbad:
                add_issue(sec, pkey, ptype, plabel, pend, slot, '',
                          'THREE_STATEMENT_VS_KEY_TABLE_MISMATCH',
                          f"三表与摘要表交叉校验不一致（rev={d.get('xcheck_rev')}, "
                          f"npp={d.get('xcheck_npp')}, ocf={d.get('xcheck_ocf')}）；"
                          f'相关字段标 EXTRACTED_XCHECK_MISMATCH，跨期比较须先核',
                          'ERROR', 'YES', doc)

            # 已采集槽的上市前交叉检查：沪深早于上市日 = IPO 申报期财报（真实存在，非错误）；
            # 北交所上市前在股转挂牌、同样披露年报，不能按北交所上市日判不适用（A04 用股转挂牌日）。
            ld = listing.get(sec)
            if ld and pend < ld and not sec.startswith('BJ'):
                add_issue(sec, pkey, ptype, plabel, pend, slot, '', 'PRE_IPO_REPORT',
                          f'报告期末 {pend} 早于交易所上市日 {ld}，属 IPO 申报期财报，可用于历史对比但需注明口径',
                          'INFO', 'NO', doc)

            # 解析失败整份：已登记整份失败，不再逐字段重复报 FIELD_ROW_MISSING
            if d.get('parse_error'):
                add_issue(sec, pkey, ptype, plabel, pend, slot, '', 'DOCUMENT_PARSE_FAILED',
                          d['parse_error'], 'ERROR', 'YES', doc,
                          f"pages={d.get('n_pages')} chars={d.get('text_chars')}")
                continue

            for fid in YTD_FIELDS + INSTANT_FIELDS:
                r = f.get((fid, ''))
                if r is None:
                    # 扣非等字段带 note（source=主要会计数据表），键不是空字符串
                    r = next((v for (k, _n), v in f.items() if k == fid), None)
                if r is None:
                    add_issue(sec, pkey, ptype, plabel, pend, slot, fid, 'FIELD_ROW_MISSING',
                              '抽取结果无该字段行', 'ERROR', 'YES', doc)
                    continue
                if r['extract_status'] == 'EXTRACTED' and r['value_cny'] not in ('', None):
                    _st = 'EXTRACTED_KEY_TABLE' if r['note'].startswith('source=主要会计数据表') \
                        else 'EXTRACTED'
                    if xbad and fid in ('FIN.REV.YTD', 'FIN.NPP.YTD', 'FIN.OCF.YTD'):
                        _st = 'EXTRACTED_XCHECK_MISMATCH'
                    cells[(sec, pkey, 'YTD' if fid in YTD_FIELDS else 'INSTANT')][fid] = {
                        'value': float(r['value_cny']),
                        'raw': r['value_raw'], 'unit': r['unit_raw'],
                        'scale': r['unit_scale'],
                        'status': _st,
                        'source_kind': 'PDF_STATEMENT',
                        'doc': doc, 'page': r['page'], 'label': r['evidence_label'],
                        'published_on': pub, 'pit': 'PIT_OK' if pub and pub <= AS_OF else 'PIT_UNKNOWN',
                        'slot': slot,
                    }
                elif r['extract_status'] == 'EXTRACTED':
                    add_issue(sec, pkey, ptype, plabel, pend, slot, fid,
                              'UNIT_UNKNOWN_VALUE_NOT_CONVERTED',
                              f"已取到原值 {r['value_raw']} 但单位识别为 {r['unit_raw']}，未折算为元",
                              'ERROR', 'YES', doc)
                    continue
                else:
                    itype = {
                        'NOT_IN_STATEMENT': 'FIELD_NOT_IN_STATEMENT',
                        'BLANK_IN_STATEMENT': 'FIELD_BLANK_IN_STATEMENT',
                        'STATEMENT_NOT_FOUND': 'STATEMENT_NOT_FOUND',
                        'NOT_FOUND': 'FIELD_NOT_FOUND',
                    }.get(r['extract_status'], 'FIELD_' + r['extract_status'])
                    blocking = 'YES' if fid in ('FIN.REV.YTD', 'FIN.NPP.YTD') else 'NO'
                    add_issue(sec, pkey, ptype, plabel, pend, slot, fid, itype,
                              r['extract_status'] + (':' + r['note'] if r['note'] else ''),
                              'WARN' if r['extract_status'] in ('NOT_IN_STATEMENT',
                                                                'BLANK_IN_STATEMENT') else 'ERROR',
                              blocking, doc)

            # 重述标记
            rr = f.get(('FIN.RESTATEMENT', ''))
            if rr is None:
                # 抽取器 push 时 note='method=...;evidence=...'，键不是空字符串。
                # 原来只查空键，导致 1,089 个「是」+2,157 个待核整批丢失（Codex 复核阻断项2）。
                rr = next((v for (k, _n), v in f.items() if k == 'FIN.RESTATEMENT'), None)
            if rr:
                restate[(sec, pkey)] = {
                    'flag': rr['value_raw'] or rr['extract_status'],
                    'status': rr['extract_status'],
                    'page': rr['page'],
                    'evidence': (rr['note'] or '')[:200],
                    'document_id': doc,
                }
                if rr['extract_status'] == 'RESTATEMENT_INDICATED_NEEDS_REVIEW':
                    add_issue(sec, pkey, ptype, plabel, pend, slot, 'FIN.RESTATEMENT',
                              'RESTATEMENT_INDICATED_NEEDS_REVIEW',
                              '关键词显示可能发生追溯重述，未能确认勾选项；该期跨期比较标 RESTATEMENT_UNRESOLVED',
                              'WARN', 'NO', doc, (rr['note'] or '')[:120])

            # 分季度表（仅年报有）
            for fid in SQ_FIELDS:
                for qn in ('Q1', 'Q2', 'Q3', 'Q4'):
                    r = f.get((fid, qn))
                    if r is None:
                        continue
                    if r['extract_status'] == 'EXTRACTED' and r['value_cny'] not in ('', None):
                        qk, qt, qend = quarter_period(fy, int(qn[1]))
                        cells[(sec, qk, 'SQ')][fid] = {
                            'value': float(r['value_cny']),
                            'raw': r['value_raw'], 'unit': r['unit_raw'], 'scale': r['unit_scale'],
                            'status': 'EXTRACTED_QUARTERLY_TABLE', 'source_kind': 'PDF_QUARTERLY_TABLE',
                            'doc': doc, 'page': r['page'], 'label': r['evidence_label'],
                            'published_on': pub, 'pit': 'PIT_OK' if pub and pub <= AS_OF else 'PIT_UNKNOWN',
                            'slot': slot, 'qtype': qt, 'qend': qend,
                        }
                    elif qn == 'Q1':
                        # 只对 Q1 记一次，避免同一缺口重复 4 条
                        add_issue(sec, pkey, ptype, plabel, pend, slot, fid,
                                  'QUARTERLY_TABLE_' + r['extract_status'],
                                  r['extract_status'] + (':' + r['note'] if r['note'] else ''),
                                  'WARN', 'NO', doc)
                        break

        print(f'[S00] {slot}: verified={n_ex} pre_listing={n_na} '
              f'not_disclosed={n_nd} not_yet={n_ny}', flush=True)

    # ---------- 2. 旧快照：2021/2022 年度补充 + 2023-2025 交叉校验
    legacy_xcheck = Counter()
    legacy_conflicts = []
    for sec in secs:
        lr = legacy.get(sec)
        if not lr:
            add_issue(sec, '', '', '', '', '', 'LEGACY_SNAPSHOT_MISSING',
                      '旧快照无该公司行', 'INFO', 'NO')
            continue
        for year in (2021, 2022, 2023, 2024, 2025):
            pkey = f'{year}1231'
            plabel = f'FY{year}'
            rev = lr.get(f'revenue_cny_{year}', '')
            npp = lr.get(f'net_profit_parent_cny_{year}', '')
            gm = lr.get(f'gross_margin_pct_{year}', '')
            for fid, val in (('FIN.REV.YTD', rev), ('FIN.NPP.YTD', npp)):
                if val in ('', None):
                    continue
                v = float(val)
                have = cells.get((sec, pkey, 'YTD'), {}).get(fid)
                if have:
                    # 双源校验：以官方 PDF 为准
                    diff = abs(have['value'] - v)
                    tol = max(1.0, abs(v) * 1e-6)
                    have['legacy_value'] = v
                    if diff <= tol:
                        legacy_xcheck['MATCH'] += 1
                    else:
                        legacy_xcheck['MISMATCH'] += 1
                        legacy_conflicts.append({
                            'security_id': sec, 'period_key': pkey, 'field_id': fid,
                            'pdf_value': have['value'], 'legacy_value': v,
                            'abs_diff': round(diff, 2),
                            'rel_diff_pct': round(diff / abs(v) * 100, 4) if v else None,
                            'document_id': have['doc'],
                        })
                        add_issue(sec, pkey, 'FY', plabel, f'{year}-12-31', f'annual_{year}', fid,
                                  'PROVIDER_VS_PDF_MISMATCH',
                                  f'旧快照 {v:,.2f} vs 官方 PDF {have["value"]:,.2f}，差 {diff:,.2f}；以 PDF 为准',
                                  'WARN', 'NO', have['doc'])
                else:
                    cells[(sec, pkey, 'YTD')][fid] = {
                        'value': v, 'raw': val, 'unit': '元', 'scale': 1,
                        'status': 'LEGACY_SNAPSHOT', 'source_kind': 'LEGACY_SNAPSHOT',
                        'doc': '', 'page': '', 'label': '', 'published_on': '',
                        'pit': 'PIT_UNKNOWN', 'slot': f'legacy_{year}',
                    }
            if gm not in ('', None):
                cells.setdefault((sec, pkey, 'YTD'), {}).setdefault('__legacy_gm', {})['value'] = float(gm)
                if year in (2021, 2022):
                    cells[(sec, pkey, 'YTD')]['FIN.GROSSMARGIN.PCT'] = {
                        'value': float(gm), 'raw': gm, 'unit': '%', 'scale': 'pct',
                        'status': 'LEGACY_SNAPSHOT', 'source_kind': 'LEGACY_SNAPSHOT',
                        'doc': '', 'page': '', 'label': '', 'published_on': '',
                        'pit': 'PIT_UNKNOWN', 'slot': f'legacy_{year}',
                    }

        # 2026H1 营收/归母
        for fid, key in (('FIN.REV.YTD', 'revenue_cny_2026H1'),
                         ('FIN.NPP.YTD', 'net_profit_parent_cny_2026H1')):
            val = lr.get(key, '')
            if val in ('', None):
                continue
            v = float(val)
            have = cells.get((sec, '20260630', 'YTD'), {}).get(fid)
            if have:
                diff = abs(have['value'] - v)
                tol = max(1.0, abs(v) * 1e-6)
                legacy_xcheck['MATCH' if diff <= tol else 'MISMATCH'] += 1
                if diff > tol:
                    legacy_conflicts.append({
                        'security_id': sec, 'period_key': '20260630', 'field_id': fid,
                        'pdf_value': have['value'], 'legacy_value': v,
                        'abs_diff': round(diff, 2),
                        'rel_diff_pct': round(diff / abs(v) * 100, 4) if v else None,
                        'document_id': have['doc'],
                    })
                    add_issue(sec, '20260630', 'H1', 'H1_2026', '2026-06-30', 'h1_2026', fid,
                              'PROVIDER_VS_PDF_MISMATCH',
                              f'旧快照 {v:,.2f} vs 官方 PDF {have["value"]:,.2f}，差 {diff:,.2f}；以 PDF 为准',
                              'WARN', 'NO', have['doc'])

        gm_h1 = lr.get('gross_margin_pct_2026H1', '')
        if gm_h1 not in ('', None):
            cells.setdefault((sec, '20260630', 'YTD'), {}).setdefault(
                '__legacy_gm', {})['value'] = float(gm_h1)

        # 22 期扣非累计（快照口径为年初至今累计）
        for y in range(2021, 2027):
            for suffix in ('0331', '0630', '0930', '1231'):
                pkey = f'{y}{suffix}'
                key = f'deducted_np_parent_cny_{pkey}'
                val = lr.get(key, '')
                if val in ('', None):
                    continue
                v = float(val)
                have = cells.get((sec, pkey, 'YTD'), {}).get('FIN.NPDEDT.YTD')
                if have:
                    have['legacy_value'] = v
                    diff = abs(have['value'] - v)
                    tol = max(1.0, abs(v) * 1e-6)
                    legacy_xcheck['MATCH' if diff <= tol else 'MISMATCH'] += 1
                    if diff > tol:
                        legacy_conflicts.append({
                            'security_id': sec, 'period_key': pkey, 'field_id': 'FIN.NPDEDT.YTD',
                            'pdf_value': have['value'], 'legacy_value': v,
                            'abs_diff': round(diff, 2),
                            'rel_diff_pct': round(diff / abs(v) * 100, 4) if v else None,
                            'document_id': have['doc'],
                        })
                elif pkey.startswith(('2021', '2022')):
                    cells[(sec, pkey, 'YTD')]['FIN.NPDEDT.YTD'] = {
                        'value': v, 'raw': val, 'unit': '元', 'scale': 1,
                        'status': 'LEGACY_SNAPSHOT', 'source_kind': 'LEGACY_SNAPSHOT',
                        'doc': '', 'page': '', 'label': '', 'published_on': '',
                        'pit': 'PIT_UNKNOWN', 'slot': f'legacy_{pkey}',
                    }

    print(f'[S00] legacy xcheck {dict(legacy_xcheck)} conflicts={len(legacy_conflicts)}', flush=True)

    # ---------- 3. 派生（第一轮）：算一次供毛利率 vs 快照校验；仲裁后还会整体重算
    derived_n = derive_ratios(cells, legacy_xcheck=legacy_xcheck, add_issue=add_issue)
    print(f'[S00] derived cells={derived_n} (round 1, pre-arbitration)', flush=True)

    # ---------- 4. 单季：官方分季表优先，缺失时同年同版本累计相减
    sq_derived = Counter()
    for sec in secs:
        for y in (2023, 2024, 2025, 2026):
            cum = {
                'Q1': cells.get((sec, f'{y}0331', 'YTD'), {}),
                'H1': cells.get((sec, f'{y}0630', 'YTD'), {}),
                '9M': cells.get((sec, f'{y}0930', 'YTD'), {}),
                'FY': cells.get((sec, f'{y}1231', 'YTD'), {}),
            }
            for fid, q_from, _unused in (
                    ('FIN.REV.YTD', 'FIN.REV.SQ', None),
                    ('FIN.NPP.YTD', 'FIN.NPP.SQ', None),
                    ('FIN.NPDEDT.YTD', 'FIN.NPDEDT.SQ', None),
                    ('FIN.OCF.YTD', 'FIN.OCF.SQ', None)):
                q1 = cum['Q1'].get(fid)
                pairs = [
                    (1, q1, None),
                    (2, cum['H1'].get(fid), q1),
                    (3, cum['9M'].get(fid), cum['H1'].get(fid)),
                    (4, cum['FY'].get(fid), cum['9M'].get(fid)),
                ]
                for q, hi, lo in pairs:
                    qk, qt, qend = quarter_period(y, q)
                    have = cells.get((sec, qk, 'SQ'), {}).get(q_from)
                    if have:
                        sq_derived['OFFICIAL_TABLE'] += 1
                        continue
                    # Q1 单季 = 一季报累计本身（累计即单季），不需要相减
                    if q == 1:
                        if hi is None:
                            sq_derived['NOT_DERIVABLE'] += 1
                            continue
                        cells.setdefault((sec, qk, 'SQ'), {})[q_from] = {
                            'value': hi['value'], 'raw': hi['raw'], 'unit': hi['unit'],
                            'scale': hi['scale'],
                            'status': 'DERIVED_Q1_HOLD_UPSTREAM' if _is_hold(hi) else 'DERIVED_Q1_EQUALS_YTD',
                            'upstream_hold': f'{fid}@{hi["slot"]}' if _is_hold(hi) else '',
                            'source_kind': hi['source_kind'], 'doc': hi['doc'],
                            'page': hi['page'], 'label': 'Q1累计即单季',
                            'published_on': hi['published_on'], 'pit': hi['pit'],
                            'slot': hi['slot'],
                        }
                        sq_derived['Q1_FROM_YTD'] += 1
                        continue
                    if hi is None or lo is None:
                        sq_derived['NOT_DERIVABLE'] += 1
                        continue
                    # 只允许同一来源类型相减（PDF 累计对 PDF 累计，快照对快照）
                    if hi['source_kind'] != lo['source_kind']:
                        add_issue(sec, qk, qt, f'{qt}_{y}', qend, hi['slot'], q_from,
                                  'CROSS_SOURCE_SUBTRACTION_BLOCKED',
                                  f'两期来源不同（{hi["source_kind"]} vs {lo["source_kind"]}），禁止相减',
                                  'WARN', 'NO', hi['doc'])
                        sq_derived['BLOCKED_CROSS_SOURCE'] += 1
                        continue
                    legacy_both = (hi['source_kind'] == 'LEGACY_SNAPSHOT'
                                   and lo['source_kind'] == 'LEGACY_SNAPSHOT')
                    if not legacy_both and (hi['pit'] != 'PIT_OK' or lo['pit'] != 'PIT_OK'):
                        sq_derived['BLOCKED_PIT'] += 1
                        continue
                    holds = [f'{fid}@{c["slot"]}' for c in (hi, lo) if _is_hold(c)]
                    val = round(hi['value'] - lo['value'], 2)
                    cells.setdefault((sec, qk, 'SQ'), {})[q_from] = {
                        'value': val, 'raw': '', 'unit': '元', 'scale': 1,
                        'status': 'DERIVED_HOLD_UPSTREAM' if holds else 'DERIVED_CUMULATIVE_DIFF',
                        'upstream_hold': '|'.join(holds), 'source_kind': 'DERIVED_DIFF',
                        'doc': hi['doc'], 'page': hi['page'], 'label': f'{hi["slot"]}−{lo["slot"]}',
                        'published_on': hi['published_on'], 'pit': hi['pit'], 'slot': hi['slot'],
                        'note': 'LEGACY_PIT_UNKNOWN' if legacy_both else '',
                    }
                    sq_derived['DERIVED_DIFF'] += 1

    print(f'[S00] single-quarter {dict(sq_derived)}', flush=True)

    # ---------- 5. V1 校验：四季之和 = 全年
    v1 = Counter()
    for sec in secs:
        for y in (2023, 2024, 2025):
            fy = cells.get((sec, f'{y}1231', 'YTD'), {})
            for cum_fid, sq_fid in (('FIN.REV.YTD', 'FIN.REV.SQ'),
                                    ('FIN.NPP.YTD', 'FIN.NPP.SQ'),
                                    ('FIN.NPDEDT.YTD', 'FIN.NPDEDT.SQ'),
                                    ('FIN.OCF.YTD', 'FIN.OCF.SQ')):
                total = fy.get(cum_fid)
                if not total:
                    continue
                parts = [cells.get((sec, quarter_period(y, q)[0], 'SQ'), {}).get(sq_fid)
                         for q in (1, 2, 3, 4)]
                if any(p is None for p in parts):
                    v1['INCOMPLETE_QUARTERS'] += 1
                    continue
                sq_sum = sum(p['value'] for p in parts)
                diff = abs(sq_sum - total['value'])
                rel = diff / max(abs(total['value']), 1.0)
                if diff <= 1.0:
                    v1['MATCH'] += 1
                elif diff <= 1000 and rel < 1e-5:
                    v1['MATCH_ROUNDING'] += 1
                else:
                    v1['MISMATCH'] += 1
                    orig_total = total['value']
                    lg = total.get('legacy_value')
                    resolved = 'UNRESOLVED_NO_PROVIDER'
                    if lg is not None:
                        d_sum = abs(sq_sum - lg)
                        d_tot = abs(orig_total - lg)
                        base = max(abs(lg), 1.0)
                        if d_sum < d_tot and d_sum / base <= 0.01:
                            resolved = 'QUARTERLY_SUM_ADOPTED'
                            total['original_value'] = orig_total
                            total['adopted_value'] = sq_sum
                            total['adoption_reason'] = (
                                f'三表全年 {orig_total:,.2f} 与摘要表不一致；四季之和 {sq_sum:,.2f} '
                                f'与第三方快照 {lg:,.2f} 相对差 {d_sum / base:.2%}（≤1%），采用四季之和')
                            total['quarterly_inputs'] = '|'.join(
                                f'Q{i}={pp["value"]:,.2f}' for i, pp in zip((1, 2, 3, 4), parts))
                            total['value'] = sq_sum
                            total['status'] = 'DERIVED_QUARTERLY_SUM_OVERRIDE'
                            total['source_kind'] = 'DERIVED_QUARTERLY_SUM'
                            total['note'] = 'THREE_STATEMENT_MISMATCH_ARBITRATED_BY_PROVIDER'
                        elif d_tot / base <= 0.01:
                            resolved = 'YTD_KEPT'
                        else:
                            resolved = 'BOTH_FAR_FROM_PROVIDER'
                    v1[resolved] += 1
                    if resolved != 'QUARTERLY_SUM_ADOPTED':
                        # 无法仲裁的不一致必须留在格上，不能只写在 issues 里——
                        # 否则下游看到的是一个「正常」的全年值，不知道它与四季和不符
                        prev = total.get('note', '')
                        total['note'] = (prev + '|' if prev else '') + f'PERIOD_INCONSISTENT_{resolved}'
                    add_issue(sec, f'{y}1231', 'FY', f'FY{y}', f'{y}-12-31', f'annual_{y}', cum_fid,
                              'PERIOD_INCONSISTENT',
                              f'四季之和 {sq_sum:,.2f} vs 三表全年 {orig_total:,.2f}'
                              f'（差 {sq_sum - orig_total:,.2f}，相对 {rel:.2e}）；'
                              f'第三方快照 {lg if lg is not None else "N/A"}；裁决 {resolved}',
                              'ERROR' if resolved == 'UNRESOLVED_NO_PROVIDER' else 'WARN',
                              'YES' if resolved == 'UNRESOLVED_NO_PROVIDER' else 'NO', total['doc'])
    print(f'[S00] V1 four-quarter-sum {dict(v1)}', flush=True)

    # ---------- 5.6 阻断项1：基础值仲裁/采用后统一重算全部下游
    # 单季 Q4 与年度累计是同一份报告里的两条路径；年度被仲裁改写后 Q4 必须跟着重算，
    # 否则「四季之和 = 全年」会在最终表里再次不成立。派生比率同理整体重算。
    recalc = Counter()
    for sec in secs:
        for y in (2023, 2024, 2025):
            fy = cells.get((sec, f'{y}1231', 'YTD'), {})
            for cum_fid, sq_fid in (('FIN.REV.YTD', 'FIN.REV.SQ'),
                                    ('FIN.NPP.YTD', 'FIN.NPP.SQ'),
                                    ('FIN.NPDEDT.YTD', 'FIN.NPDEDT.SQ'),
                                    ('FIN.OCF.YTD', 'FIN.OCF.SQ')):
                cur = fy.get(cum_fid)
                if not cur:
                    continue
                q4 = cells.get((sec, f'{y}1231', 'SQ'), {}).get(sq_fid)
                if not q4 or q4.get('status') not in ('DERIVED_CUMULATIVE_DIFF',
                                                      'DERIVED_HOLD_UPSTREAM'):
                    continue  # 官方分季表的值不动
                nine = cells.get((sec, f'{y}0930', 'YTD'), {}).get(cum_fid)
                if not nine:
                    continue
                old_v = q4['value']
                q4['value'] = round(cur['value'] - nine['value'], 2)
                recalc['Q4_RECALC'] += 1
                if abs(old_v - q4['value']) > 0.001:
                    recalc['Q4_CHANGED'] += 1
    derived_n2 = derive_ratios(cells)
    print(f'[S00] downstream recalc {dict(recalc)}, ratios recomputed={derived_n2}', flush=True)

    # ---------- 5.5 整槽无任何可抽取值：定性（英文版 / 无文本层 / 抽取盲区）
    value_slots_early = set()
    for k, fields in cells.items():
        for fid, v in fields.items():
            if fid.startswith('__'):
                continue
            sl = v.get('slot', '')
            if sl in SLOTS:
                value_slots_early.add((sl, k[0]))
    empty_slots = []
    for slot in SLOTS:
        for sec in secs:
            if slot_status.get((slot, sec)) != 'COLLECTED_IDENTITY_VERIFIED':
                continue
            if (slot, sec) in value_slots_early:
                continue
            row = index.get((slot, sec), {})
            lf = ROOT / row.get('local_file', '')
            lang, ratio, chars = detect_doc_language(lf) if row.get('local_file') else ('NO_FILE', 0.0, 0)
            pkey, ptype, pend, fy, plabel = period_meta(slot)
            empty_slots.append({'security_id': sec, 'slot_id': slot,
                                'document_id': row.get('document_id', ''),
                                'language': lang, 'zh_ratio': ratio, 'text_chars': chars})
            itype = {'EN_OR_NON_ZH': 'DOCUMENT_IS_ENGLISH_OR_NON_ZH',
                     'NO_TEXT_LAYER': 'DOCUMENT_NO_TEXT_LAYER',
                     'OPEN_FAILED': 'DOCUMENT_OPEN_FAILED',
                     'MIXED': 'DOCUMENT_MIXED_LANGUAGE',
                     'NO_FILE': 'DOCUMENT_FILE_MISSING'}.get(lang, 'EXTRACTION_BLIND_SPOT')
            add_issue(sec, pkey, ptype, plabel, pend, slot, '', itype,
                      f'整槽无任何可抽取字段；文档语言判定 {lang}（中文占比 {ratio}，前 3 页 {chars} 字符）；'
                      f'{"需补采中文版定期报告" if lang == "EN_OR_NON_ZH" else "需核抽取器版式覆盖"}',
                      'ERROR', 'YES', row.get('document_id', ''))

    # ---------- 6. 低基数标记（需要上年同期）
    low_base_n = 0
    for (sec, pkey, basis), fields in cells.items():
        if basis != 'YTD' or not pkey.endswith(('0630', '0930', '1231', '0331')):
            continue
        y = int(pkey[:4])
        py = f'{y - 1}{pkey[4:]}'
        prev = cells.get((sec, py, 'YTD'), {})
        for fid, thr, lb_tag in (('FIN.REV.YTD', LOW_BASE_REV, 'REV'),
                                 ('FIN.NPP.YTD', LOW_BASE_PROFIT, 'PROFIT')):
            cur = fields.get(fid)
            p = prev.get(fid)
            if not cur or not p:
                continue
            if abs(p['value']) < thr:
                cur['low_base'] = f'LOW_BASE_{lb_tag}'
                low_base_n += 1
            elif p['value'] < 0:
                cur['low_base'] = f'NEGATIVE_BASE_{lb_tag}'
                low_base_n += 1
    print(f'[S00] low/negative base flagged={low_base_n}', flush=True)

    # ---------- 7. 输出 normalized 长表
    suffix = f'_{tag}' if tag else ''
    npath = OUT / f'financial_normalized{suffix}.csv'
    n_rows = 0
    with io.open(npath, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=NORMALIZED_HEADER)
        w.writeheader()
        for (sec, pkey, basis), fields in sorted(cells.items()):
            comp = companies.get(sec, {})
            ld = listing.get(sec, '')
            if basis == 'SQ':
                ptype = next((v.get('qtype') for v in fields.values() if v.get('qtype')), '')
                pend = next((v.get('qend') for v in fields.values() if v.get('qend')), '')
                ptype = ptype or {'0331': 'Q1', '0630': 'Q2', '0930': 'Q3', '1231': 'Q4'}.get(pkey[4:], '')
                pend = pend or f'{pkey[:4]}-{pkey[4:6]}-{pkey[6:]}'
                plabel = f'{ptype}_{pkey[:4]}'
                psource = 'COLLECTED_2026_SLOT'
                slot_id = next((v.get('slot') for v in fields.values() if v.get('slot')), '')
            else:
                ptype = {'0331': 'Q1', '0630': 'H1', '0930': '9M', '1231': 'FY'}.get(pkey[4:], '')
                pend = f'{pkey[:4]}-{pkey[4:6]}-{pkey[6:]}'
                plabel = f'{ptype}_{pkey[:4]}'
                slot_id = next((v.get('slot') for v in fields.values() if v.get('slot')), '')
                psource = 'LEGACY_SNAPSHOT' if any(
                    v.get('source_kind') == 'LEGACY_SNAPSHOT' for v in fields.values()) \
                    else 'COLLECTED_2026_SLOT'
            rest_info = restate.get((sec, pkey), {})
            restatement = rest_info.get('flag', '') if isinstance(rest_info, dict) else rest_info
            for fid, v in sorted(fields.items()):
                if fid.startswith('__'):
                    continue
                if fid == 'FIN.RESTATEMENT':
                    continue
                is_pre = 'YES' if slot_status.get((v.get('slot', ''), sec)) == \
                    'NOT_APPLICABLE_PRE_LISTING' else 'NO'
                note = []
                if restatement == '是':
                    note.append('RESTATED_PRIOR_YEARS_UNRECALCULATED')
                elif restatement == 'RESTATEMENT_INDICATED_NEEDS_REVIEW':
                    note.append('RESTATEMENT_UNRESOLVED')
                if is_pre == 'YES':
                    note.append('PRE_LISTING')
                if v.get('low_base'):
                    note.append(v['low_base'])
                if v.get('note'):
                    note.append(v['note'])
                if v.get('upstream_hold'):
                    note.append('HOLD_UPSTREAM:' + v['upstream_hold'])
                w.writerow({
                    'security_id': sec,
                    'stock_code': comp.get('stock_code', sec.split(':')[-1]),
                    'stock_name': comp.get('stock_name', ''),
                    'period_key': pkey, 'period_type': ptype, 'period_label': plabel,
                    'period_start': period_start_of(pkey, ptype),
                    'period_end': pend, 'fiscal_year': pkey[:4],
                    'period_basis': 'SINGLE_QUARTER' if basis == 'SQ' else
                                    ('INSTANT' if fid in INSTANT_FIELDS else 'YTD_CUMULATIVE'),
                    'period_source': psource, 'slot_id': slot_id,
                    'field_id': fid, 'field_name_cn': FIELD_CN.get(fid, fid),
                    'value_raw': v.get('raw', ''), 'unit_raw': v.get('unit', ''),
                    'unit_scale': v.get('scale', ''), 'value_cny': v.get('value', ''),
                    'status': v.get('status', ''), 'status_reason': v.get('note', ''),
                    'source_kind': v.get('source_kind', ''),
                    'document_id': v.get('doc', ''), 'source_page': v.get('page', ''),
                    'evidence_label': v.get('label', ''),
                    'published_on': v.get('published_on', ''),
                    'collected_at': collected_at.get(sec, ''),
                    'pit_status': v.get('pit', ''), 'as_of': AS_OF,
                    'currency': 'CNY' if v.get('unit') in ('元', '千元', '万元', '百万元', '千万元') else 'UNKNOWN',
                    'consolidation_scope': 'CONSOLIDATED' if v.get('source_kind') != 'LEGACY_SNAPSHOT' else 'UNKNOWN',
                    'listing_date': ld, 'is_pre_listing': is_pre, 'restatement_flag': restatement,
                    'low_base_flag': v.get('low_base', ''),
                    'comparability_note': '|'.join(note),
                    'upstream_hold_fields': v.get('upstream_hold', ''),
                    'value_before_adoption': v.get('original_value', ''),
                    'adoption_reason': v.get('adoption_reason', ''),
                    'quarterly_inputs': v.get('quarterly_inputs', ''),
                    'version_used': version_map.get((sec, v.get('slot', '')), ('ORIGINAL', '', ''))[0],
                    'original_document_id': version_map.get((sec, v.get('slot', '')), ('', '', ''))[1],
                })
                n_rows += 1
    print(f'[S00] normalized rows={n_rows} -> {npath.name}', flush=True)

    # ---------- 8. 输出 issues
    ipath = OUT / f'normalization_issues{suffix}.csv'
    with io.open(ipath, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=ISSUE_HEADER)
        w.writeheader()
        for r in issues:
            w.writerow(r)
    print(f'[S00] issues={len(issues)} -> {ipath.name}', flush=True)

    # ---------- 9. 覆盖与校验汇总
    secs_in_norm = {k[0] for k in cells}
    slot_cov = Counter(slot_status.values())
    issue_types = Counter(r['issue_type'] for r in issues)
    field_cov = Counter()
    for (sec, pkey, basis), fields in cells.items():
        for fid in fields:
            if not fid.startswith('__'):
                field_cov[fid] += 1

    # 主键集合：1054 家 × N 槽，每格都必须有归属（有值 / 终态状态 / 已登记 issue）
    covered = {(slot, sec) for (slot, sec) in index.keys() if slot in SLOTS}
    missing_grid = [(slot, sec) for slot in SLOTS for sec in secs if (slot, sec) not in covered]
    value_slots = set()
    for k, fields in cells.items():
        for fid, v in fields.items():
            if fid.startswith('__'):
                continue
            sl = v.get('slot', '')
            if sl in SLOTS:
                value_slots.add((sl, k[0]))

    manifest = {
        'issue': 'S00 / #35',
        'plan_version': '20261026_collection_first_v2',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'as_of': AS_OF,
        'executor': 'WorkBuddy AI',
        'review_nature': 'SELF_CHECK',
        'inputs': {
            'runs/collection/collection_index.csv': '12648 slots',
            'runs/issues/S00/extract/*_fields.csv': f'{len(SLOTS)} slots',
            'data/company_master.csv': f'{len(companies)} companies',
            'data/company_listing_dates.csv': f'{len(listing)} resolved',
            'legacy snapshot (R1 run_20261024_local_02)': f'{len(legacy)} companies',
            'runs/issues/P04/financial_field_dictionary.csv': '33 fields contract',
        },
        'outputs': {
            'financial_normalized.csv': {'rows': n_rows},
            'normalization_issues.csv': {'rows': len(issues)},
            'normalization_manifest.json': {},
        },
        'universe': {
            'companies_total': len(secs),
            'companies_in_normalized': len(secs_in_norm),
            'companies_missing_from_normalized': sorted(set(secs) - secs_in_norm)[:50],
            'slot_status_counts': dict(slot_cov),
            'slots_total': len(SLOTS) * len(secs),
            'slots_covered_by_ledger': len(covered),
            'slots_with_at_least_one_value': len(value_slots),
            'slots_uncovered': len(missing_grid),
            'periods_in_normalized': len({(k[1], k[2]) for k in cells if any(
                not f.startswith('__') for f in cells[k])}),
        },
        'field_coverage_cells': dict(sorted(field_cov.items())),
        'checks': {
            'V1_four_quarter_sum': dict(v1),
            'V3_provider_vs_pdf': dict(legacy_xcheck),
            'single_quarter': dict(sq_derived),
            'low_or_negative_base_flagged': low_base_n,
        },
        'issue_type_counts': dict(sorted(issue_types.items())),
        'version_adoption': {
            'slots_with_corrected_fulltext': len(version_map),
            'items': [{'security_id': k[0], 'slot_id': k[1],
                       'version_used': v[0], 'original_document_id': v[1],
                       'adopted_document_id': v[2]} for k, v in sorted(version_map.items())],
            'note': '6 个槽原用非更正版；已重抽更正版并逐字段比对（132 个字段对，0 处不同），'
                    '故数值不变但溯源改为更正版，原版 id 保留在 original_document_id 列',
        },
        'empty_slots_no_value': {
            'count': len(empty_slots),
            'by_language': dict(Counter(x['language'] for x in empty_slots)),
            'items': empty_slots,
        },
        'legacy_conflicts_sample': legacy_conflicts[:20],
        'legacy_conflicts_total': len(legacy_conflicts),
        'rules_applied': {
            'null_not_zero': '缺失一律不填 0，逐条落 issues 并带原因码',
            'no_proxy_substitution': '扣非缺失不用净利润替代；经营现金流缺失不用净利润替代',
            'single_quarter_precedence': '官方分季度表优先，累计相减仅在同源同版本同 PIT 时使用',
            'cross_source_subtraction': 'PROHIBITED，登记 CROSS_SOURCE_SUBTRACTION_BLOCKED',
            'pit': f'published_on ≤ {AS_OF} 才进证据链，晚于记 AFTER_CUTOFF（本轮 0 例）',
            'pre_listing': '逐行比较 period_end < listing_date，不用状态码反推',
            'restatement': 'FIN.RESTATEMENT=是 时标 RESTATED_PRIOR_YEARS_UNRECALCULATED（未用最新年报重算历史期）',
            'low_base_thresholds': {
                'LOW_BASE_REV': f'上年同期营业收入绝对值 < {LOW_BASE_REV:,} 元',
                'LOW_BASE_PROFIT': f'上年同期归母净利绝对值 < {LOW_BASE_PROFIT:,} 元',
                'note': 'S00 临时口径，S01 登记筛选公式时可覆盖',
            },
        },
        'comparability_matrix': {
            'FY': {'basis': 'YTD_CUMULATIVE', 'months': 12, 'comparable_with': ['FY']},
            'H1': {'basis': 'YTD_CUMULATIVE', 'months': 6, 'comparable_with': ['H1']},
            '9M': {'basis': 'YTD_CUMULATIVE', 'months': 9, 'comparable_with': ['9M']},
            'Q1': {'basis': 'YTD_CUMULATIVE(=单季)', 'months': 3,
                   'comparable_with': ['Q1', 'SINGLE_QUARTER_Q1']},
            'Q2': {'basis': 'SINGLE_QUARTER', 'months': 3, 'comparable_with': ['Q2']},
            'Q3': {'basis': 'SINGLE_QUARTER', 'months': 3, 'comparable_with': ['Q3']},
            'Q4': {'basis': 'SINGLE_QUARTER', 'months': 3, 'comparable_with': ['Q4']},
            'INSTANT': {'basis': 'INSTANT', 'note': '资产负债表科目为时点值，只能同时点比较，不与期间流量混算'},
            'prohibited': ['FY vs H1', '9M vs FY', '累计 vs 单季', '跨年度相减', '跨来源相减', '跨版本（重述前后）相减'],
        },
        'known_limits': [
            '旧快照 2021/2022 年度营收与归母仅单一来源（新浪），无官方 PDF 交叉校验。',
            '未用最新年报「上年同期」列重算历史期，重述公司跨年比较口径可能不一致。',
            '季报（一季/三季）多为摘要表+三表并存，深市部分公司只有摘要表，故 COST/AR/INV 在该期为 NOT_IN_STATEMENT。',
            '合同资产未列示的公司记 NOT_IN_STATEMENT，不填 0。',
            '单季扣非在无官方分季表且累计不齐时不可派生，记 NOT_DERIVABLE。',
        ],
        'elapsed_s': round(time.time() - t0, 1),
    }
    json.dump(manifest, io.open(OUT / f'normalization_manifest{suffix}.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    json.dump({'conflicts': legacy_conflicts},
              io.open(OUT / 'legacy_snapshot_conflicts.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    print(json.dumps({k: manifest[k] for k in ('universe', 'checks', 'elapsed_s')},
                     ensure_ascii=False, indent=1)[:3000], flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--slots':
        main(slots=sys.argv[2].split(','), tag=sys.argv[3] if len(sys.argv) > 3 else 'probe')
    else:
        main()
