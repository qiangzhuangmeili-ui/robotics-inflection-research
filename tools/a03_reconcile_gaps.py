"""A03 缺口核销：把「文档层缺口」和「字段层缺口」摊平成一张可核销清单，并做去重与登记表对账。

输入（只读）：
    runs/collection/collection_index.csv      共享台账 7378 槽
    data/document_registry.csv                历史文档登记表 158 行
    data/manual_requests.csv                  历史人工补件请求 28 行
    runs/issues/A03/financial_fields_extracted*.csv   抽取器产出（可选）

输出：
    runs/issues/A03/remaining_gaps.csv        全部保留缺口，逐条带原因与下一步
    runs/issues/A03/registry_updates.csv      登记表建议更新（本轮不改原始输入）
    runs/issues/A03/dedup_report.json         去重与双轨对账结果

原则：不适用/未披露不算缺件；字段缺失不填 0；未尝试不算已取得。
"""
import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/A03'

INDEX = ROOT / 'runs/collection/collection_index.csv'
REGISTRY = ROOT / 'data/document_registry.csv'
MANUAL = ROOT / 'data/manual_requests.csv'

GAP_HEADER = ['gap_id', 'gap_layer', 'security_id', 'stock_code', 'slot_id', 'report_type',
              'period_label', 'gap_type', 'status_code', 'reason', 'evidence_ref',
              'blocking_for_next_stage', 'resolvable_by', 'next_action']

REG_HEADER = ['update_id', 'target_file', 'key_type', 'key_value', 'field', 'old_value',
              'new_value', 'change_kind', 'reason', 'source_issue', 'applied']

# 文档层终态 → 是否为「缺口」
DOC_TERMINAL = {
    'COLLECTED_IDENTITY_VERIFIED': None,            # 已取得，不是缺口
    'NOT_APPLICABLE_PRE_LISTING': 'NOT_APPLICABLE',  # 不适用，不是缺口
    'NOT_DISCLOSED_BY_ISSUER': 'NOT_DISCLOSED',      # 未披露，不是缺口
    'COLLECTED_PENDING_IDENTITY': 'PENDING_IDENTITY',
    'SOURCE_FAILED': 'SOURCE_FAILED',
    'NOT_TRIED': 'NOT_TRIED',
    'ACCESS_BLOCKED': 'ACCESS_BLOCKED',
}

# 字段层：这些状态不是缺口（已取得或该报表确实没有该科目）
FIELD_NOT_GAP = {'EXTRACTED', 'NOT_IN_STATEMENT', 'BLANK_IN_STATEMENT', 'NOT_APPLICABLE'}


def load_index():
    return list(csv.DictReader(io.open(INDEX, encoding='utf-8-sig')))


def load_registry():
    return list(csv.DictReader(io.open(REGISTRY, encoding='utf-8-sig')))


PERIOD2SLOT = {'2025年度': 'annual_2025', '2026H1': 'h1_2026', '2026半年度': 'h1_2026',
               '2026年度': 'annual_2026', '2024年度': 'annual_2024', '2023年度': 'annual_2023',
               '2024半年度': 'h1_2024', '2025半年度': 'h1_2025'}


def registry_crosswalk(idx, reg):
    """把「只在登记表、不在台账」的 97 行逐行定性。

    实测其中 71 行与台账同槽位的 sha256 完全相同——同一份文件被两个 document_id 各登记一次，
    这是真正的重复登记，必须在核销清单里显式列出，不能因为「两边都能打开」就算已核销。
    """
    idx_ids = set(r['document_id'] for r in idx if r.get('document_id'))
    byslot = defaultdict(list)
    for r in idx:
        byslot[(r['security_id'], r['slot_id'])].append(r)

    rows = []
    for r in reg:
        if r['document_id'] in idx_ids:
            continue
        period_raw = r['period_covered'] or ''
        # 带下划线后缀的是投资者关系/上市前材料等非标准期次，不能映射到定期报告槽位
        period = period_raw.split('_')[0]
        has_suffix = '_' in period_raw
        slot = None if has_suffix else PERIOD2SLOT.get(period)
        cand = byslot.get((r['security_id'], slot), []) if slot else []
        if has_suffix:
            verdict, canonical = 'NON_STANDARD_PERIOD_DOC', ''
        elif not cand:
            verdict, canonical = 'NO_MATCHING_SLOT_IN_INDEX', ''
        elif not r.get('sha256'):
            verdict, canonical = 'REGISTRY_ROW_WITHOUT_SHA256', cand[0]['document_id']
        elif r['sha256'] in {c['sha256'] for c in cand}:
            verdict, canonical = 'SAME_FILE_TWO_IDS', cand[0]['document_id']
        else:
            verdict, canonical = 'DIFFERENT_BINARY_SAME_SLOT', cand[0]['document_id']
        rows.append({
            'registry_document_id': r['document_id'],
            'security_id': r['security_id'],
            'stock_name': r.get('stock_name', ''),
            'period_covered': period_raw,
            'mapped_slot_id': slot or '',
            'registry_sha256': r.get('sha256', ''),
            'registry_drive_file_id': r.get('drive_file_id', ''),
            'registry_archive_status': r.get('archive_status', ''),
            'ledger_document_id': canonical,
            'ledger_sha256': next((c['sha256'] for c in cand
                                   if c['document_id'] == canonical), ''),
            'verdict': verdict,
            'recommended_action': {
                'SAME_FILE_TWO_IDS': '以台账 ID 为 canonical，旧 ID 保留为别名，不重编号、不重复下载',
                'DIFFERENT_BINARY_SAME_SLOT': '两份二进制不同，须比对版本/来源后择一，不得跨版本相减',
                'NO_MATCHING_SLOT_IN_INDEX': '历史遗留文档，保留原状；不并入本轮全池统计',
                'REGISTRY_ROW_WITHOUT_SHA256': '缺内容指纹，须补算后再判重',
                'NON_STANDARD_PERIOD_DOC': '投资者关系/上市前材料等非定期报告，不参与定期报告槽位判重',
            }[verdict],
        })
    return rows


def doc_gaps(idx):
    rows = []
    n = 0
    for r in idx:
        kind = DOC_TERMINAL.get(r['status'], 'UNKNOWN_STATUS')
        if kind is None:
            continue
        n += 1
        blocking = 'YES' if kind in ('PENDING_IDENTITY', 'SOURCE_FAILED', 'NOT_TRIED',
                                     'ACCESS_BLOCKED', 'UNKNOWN_STATUS') else 'NO'
        rows.append({
            'gap_id': f'DOC-{n:05d}',
            'gap_layer': 'DOCUMENT',
            'security_id': r['security_id'],
            'stock_code': r['security_id'].split(':')[1],
            'slot_id': r['slot_id'],
            'report_type': r['report_type'],
            'period_label': r['period_label'],
            'gap_type': kind,
            'status_code': r['status'],
            'reason': (r.get('status_reason') or '')[:200],
            'evidence_ref': 'runs/collection/collection_index.csv',
            'blocking_for_next_stage': blocking,
            'resolvable_by': 'NONE_TERMINAL' if blocking == 'NO' else 'AUTO_RETRY_THEN_P03',
            'next_action': ('无需补件：终态已判定，不向用户索取' if blocking == 'NO'
                            else '先自动重试/换源；仍失败再交技术复核'),
        })
    return rows


def field_gaps(field_csv):
    """字段层缺口：抽取器判定为失败/需复核的，逐条列出。"""
    if not field_csv or not Path(field_csv).exists():
        return [], {}
    rows = list(csv.DictReader(io.open(field_csv, encoding='utf-8-sig')))
    # 分季度字段一行一个季度，按 (document, field) 聚合
    agg = defaultdict(set)
    meta = {}
    for r in rows:
        k = (r['document_id'], r['field_id'])
        agg[k].add(r.get('extract_status') or r.get('status') or '')
        meta[k] = r
    out = []
    n = 0
    for (doc_id, fid), sts in agg.items():
        if sts <= FIELD_NOT_GAP:
            continue
        m = meta[(doc_id, fid)]
        n += 1
        status = '|'.join(sorted(sts))
        kind = ('RESTATEMENT_NEEDS_REVIEW' if 'RESTATEMENT_INDICATED_NEEDS_REVIEW' in status
                else 'FIELD_NOT_EXTRACTED')
        out.append({
            'gap_id': f'FLD-{n:05d}',
            'gap_layer': 'FIELD',
            'security_id': m['security_id'],
            'stock_code': m['stock_code'],
            'slot_id': m['slot_id'],
            'report_type': 'ANNUAL_REPORT',
            'period_label': m['period_label'],
            'gap_type': kind,
            'status_code': status,
            'reason': (m.get('note') or '')[:200],
            'evidence_ref': f"runs/issues/A03/{Path(field_csv).name}#{doc_id}:{fid}",
            'blocking_for_next_stage': 'NO' if kind == 'RESTATEMENT_NEEDS_REVIEW' else 'YES',
            'resolvable_by': ('S00_MANUAL_REVIEW' if kind == 'RESTATEMENT_NEEDS_REVIEW'
                              else 'A03_EXTRACTOR_FIX'),
            'next_action': ('S00 标准化时按附注逐份复核版本口径' if kind == 'RESTATEMENT_NEEDS_REVIEW'
                            else '补抽取规则或登记为需 OCR/人工取数'),
        })
    return out, {'documents_with_field_gaps': len({r['security_id'] for r in out})}


def dedup(idx, reg):
    """去重与双轨对账。"""
    doc_ids = Counter(r['document_id'] for r in idx if r.get('document_id'))
    dup_doc = {k: v for k, v in doc_ids.items() if v > 1}
    sha = Counter(r['sha256'] for r in idx if r.get('sha256'))
    dup_sha = {k: v for k, v in sha.items() if v > 1}
    # 同一 (security_id, slot_id) 多行？
    slot = Counter((r['security_id'], r['slot_id']) for r in idx)
    dup_slot = {f'{k[0]}|{k[1]}': v for k, v in slot.items() if v > 1}

    idx_ids = set(doc_ids)
    reg_ids = set(r['document_id'] for r in reg)
    both = idx_ids & reg_ids
    only_reg = reg_ids - idx_ids
    only_idx = idx_ids - reg_ids

    # 历史补件请求 28 家 → 现在是否已有已核槽
    verified_by_sec = defaultdict(int)
    for r in idx:
        if r['status'] == 'COLLECTED_IDENTITY_VERIFIED':
            verified_by_sec[r['security_id']] += 1
    manual = list(csv.DictReader(io.open(MANUAL, encoding='utf-8-sig')))
    hist = []
    for m in manual:
        sec = m['security_id']
        hist.append({
            'request_id': m['request_id'],
            'security_id': sec,
            'stock_name': m.get('stock_name', ''),
            'old_status': m.get('status', ''),
            'verified_slots_now': verified_by_sec.get(sec, 0),
            'still_needs_human': verified_by_sec.get(sec, 0) == 0,
        })

    return {
        'index_rows': len(idx),
        'registry_rows': len(reg),
        'duplicate_document_id_in_index': dup_doc,
        'duplicate_sha256_in_index': dup_sha,
        'duplicate_security_slot': dup_slot,
        'document_id_overlap': {
            'in_both': len(both),
            'only_in_registry': len(only_reg),
            'only_in_index': len(only_idx),
        },
        'registry_only_sample': sorted(only_reg)[:10],
        'index_only_count': len(only_idx),
        'historical_manual_requests': {
            'rows': len(hist),
            'companies_already_have_verified_slots': sum(1 for h in hist if not h['still_needs_human']),
            'companies_still_needing_human': sum(1 for h in hist if h['still_needs_human']),
        },
        'note': ('document_registry 与 collection_index 是双轨：全池 7223 份已核文档只登记在 '
                 'collection_index，未回写 document_registry。A03 不批量写 7223 行，只出对账结论。'),
    }


def registry_updates(idx, reg, dedup_res):
    """登记表建议更新（本轮不改原始输入，逐条可执行）。"""
    rows = []
    n = 0
    # 1) 双轨未回写：collection_index 独有的已核文档需要登记到 document_registry
    idx_ids = set(r['document_id'] for r in idx if r.get('document_id'))
    reg_ids = set(r['document_id'] for r in reg)
    only_idx = idx_ids - reg_ids
    n += 1
    rows.append({
        'update_id': f'REG-{n:05d}',
        'target_file': 'data/document_registry.csv',
        'key_type': 'BULK_BY_DOCUMENT_ID',
        'key_value': f'{len(only_idx)} document_ids',
        'field': 'ALL',
        'old_value': 'NOT_REGISTERED',
        'new_value': 'REGISTER_FROM_COLLECTION_INDEX',
        'change_kind': 'BACKLOG',
        'reason': ('collection_index 已核文档未回写登记表；需按 P01 三层身份模型批量补登，'
                   '本次不执行以免擅自改写原始输入'),
        'source_issue': 'A03',
        'applied': 'NO',
    })
    # 2) Drive 归档态：全池未上传，不得写 VERIFIED
    n += 1
    rows.append({
        'update_id': f'REG-{n:05d}',
        'target_file': 'runs/collection/collection_index.csv',
        'key_type': 'ALL_ROWS',
        'key_value': 'archive_status',
        'field': 'archive_status',
        'old_value': 'EMPTY',
        'new_value': 'NOT_UPLOADED_ACCESS_BLOCKED',
        'change_kind': 'BLOCKED',
        'reason': ('Drive 无可用 API 凭据（302→ServiceLogin/401/403），本轮未上传任何文件；'
                   'archive_status 不得写 VERIFIED'),
        'source_issue': 'A03',
        'applied': 'NO',
    })
    # 3) 字段层：抽取结果可回写为字段可用性标记
    n += 1
    rows.append({
        'update_id': f'REG-{n:05d}',
        'target_file': 'runs/collection/collection_index.csv',
        'key_type': 'ALL_ROWS',
        'key_value': 'field_extraction_status',
        'field': 'field_extraction_status',
        'old_value': 'EMPTY',
        'new_value': 'SEE_A03_financial_fields_extracted',
        'change_kind': 'PROPOSED',
        'reason': '字段级抽取结果单独成表，未回写台账；S00 以该表为输入',
        'source_issue': 'A03',
        'applied': 'NO',
    })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fields', default='')
    ap.add_argument('--tag', default='')
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    idx = load_index()
    reg = load_registry()

    dg = doc_gaps(idx)
    fg, fstats = field_gaps(args.fields) if args.fields else ([], {})
    xw = registry_crosswalk(idx, reg)
    dup_gaps = []
    for i, r in enumerate(xw, 1):
        if r['verdict'] != 'SAME_FILE_TWO_IDS':
            continue
        dup_gaps.append({
            'gap_id': f'DUP-{i:05d}',
            'gap_layer': 'REGISTRY_DUPLICATE',
            'security_id': r['security_id'],
            'stock_code': r['security_id'].split(':')[1],
            'slot_id': r['mapped_slot_id'],
            'report_type': '',
            'period_label': r['period_covered'],
            'gap_type': 'SAME_FILE_TWO_IDS',
            'status_code': 'DUPLICATE_REGISTRATION',
            'reason': (f"登记表 {r['registry_document_id']} 与台账 {r['ledger_document_id']} "
                       f"sha256 相同，同一文件两个 ID"),
            'evidence_ref': 'runs/issues/A03/registry_crosswalk.csv',
            'blocking_for_next_stage': 'NO',
            'resolvable_by': 'S00_USE_LEDGER_ID_AS_CANONICAL',
            'next_action': '以台账 ID 为 canonical，旧 ID 留别名，不重编号、不重复下载',
        })
    gaps = dg + dup_gaps + fg

    gpath = OUT / f'remaining_gaps{args.tag}.csv'
    with io.open(gpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=GAP_HEADER)
        w.writeheader()
        for r in gaps:
            w.writerow(r)

    xw_path = OUT / f'registry_crosswalk{args.tag}.csv'
    if xw:
        with io.open(xw_path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(xw[0].keys()))
            w.writeheader()
            w.writerows(xw)

    dd = dedup(idx, reg)
    dd['registry_crosswalk'] = dict(Counter(r['verdict'] for r in xw))
    ru = registry_updates(idx, reg, dd)
    rpath = OUT / f'registry_updates{args.tag}.csv'
    with io.open(rpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=REG_HEADER)
        w.writeheader()
        for r in ru:
            w.writerow(r)

    json.dump(dd, io.open(OUT / f'dedup_report{args.tag}.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    st = Counter((r['gap_layer'], r['gap_type']) for r in gaps)
    print(json.dumps({
        'index_rows': len(idx),
        'doc_gaps': len(dg),
        'field_gaps': len(fg),
        'gap_breakdown': {f'{k[0]}|{k[1]}': v for k, v in st.items()},
        'dedup': dd,
        'registry_crosswalk': dict(Counter(r['verdict'] for r in xw)),
        'registry_update_rows': len(ru),
        'field_stats': fstats,
    }, ensure_ascii=False, indent=1)[:3000])
    print(f'[A03] wrote {gpath.name} {rpath.name}')


if __name__ == '__main__':
    main()
