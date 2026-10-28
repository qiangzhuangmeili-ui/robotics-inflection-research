"""S00 全池财务字段抽取（复用 A03 抽取器，按槽位分批落盘，支持断点续跑）。

与 A03 的差别：
1. 输出到 runs/issues/S00/extract/<slot>.csv，每槽一份，已存在且行数达标则跳过；
2. 覆盖全部 12 个槽（年报 3 + 半年报 3 + 一季报 3 + 三季报 3），A03 只跑过年报；
3. 只读已核原件（COLLECTED_IDENTITY_VERIFIED），不下载、不改原件、不写回台账。

用法：
    python tools/s00_extract.py --slots h1_2026 --limit 4 --tag probe
    python tools/s00_extract.py --all --workers 14
"""
import argparse
import csv
import io
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import a03_financial_field_extractor as A03  # noqa: E402

OUT = ROOT / 'runs/issues/S00/extract'
INDEX = ROOT / 'runs/collection/collection_index.csv'

FIELDS_HEADER = A03.FIELDS_HEADER
DIAG_HEADER = A03.DIAG_HEADER

ALL_SLOTS = ['annual_2023', 'annual_2024', 'annual_2025',
             'h1_2024', 'h1_2025', 'h1_2026',
             'q1_2024', 'q1_2025', 'q1_2026',
             'q3_2024', 'q3_2025', 'q3_2026']


def write_slot(slot, results, tag=''):
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = f'_{tag}' if tag else ''
    fpath = OUT / f'{slot}{suffix}_fields.csv'
    dpath = OUT / f'{slot}{suffix}_diag.csv'
    jpath = OUT / f'{slot}{suffix}_summary.json'

    n_fields = 0
    with io.open(fpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS_HEADER)
        w.writeheader()
        for r in results:
            for row in r.get('fields', []):
                w.writerow(row)
                n_fields += 1

    with io.open(dpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=DIAG_HEADER)
        w.writeheader()
        for r in results:
            reg = r.get('regions', {})
            xc = r.get('crosscheck', {})
            w.writerow({
                'document_id': r['document_id'], 'security_id': r['security_id'],
                'stock_code': r['stock_code'], 'slot_id': r['slot_id'],
                'period_label': r['period_label'], 'n_pages': r.get('n_pages', 0),
                'text_chars': r.get('text_chars', 0), 'parse_error': r.get('parse_error') or '',
                'quarterly_page': r.get('quarterly_page') or '',
                'restatement': r.get('restatement') or '',
                'restatement_method': r.get('restatement_method') or '',
                'unit_bs': r.get('unit_bs') or '', 'unit_is': r.get('unit_is') or '',
                'unit_cf': r.get('unit_cf') or '', 'unit_q': r.get('unit_q') or '',
                'key_financials_page': r.get('key_financials_page') or '',
                'key_financials_unit': r.get('key_financials_unit') or '',
                'elapsed_s': r.get('elapsed_s', 0),
                'bs_start': reg.get('BS_CONS', {}).get('start_page', ''),
                'bs_end': reg.get('BS_CONS', {}).get('end_page', ''),
                'is_start': reg.get('IS_CONS', {}).get('start_page', ''),
                'is_end': reg.get('IS_CONS', {}).get('end_page', ''),
                'cf_start': reg.get('CF_CONS', {}).get('start_page', ''),
                'cf_end': reg.get('CF_CONS', {}).get('end_page', ''),
                'xcheck_rev': xc.get('FIN.REV.YTD', ''),
                'xcheck_npp': xc.get('FIN.NPP.YTD', ''),
                'xcheck_ocf': xc.get('FIN.OCF.YTD', ''),
                'xcheck_pass': A03.xcheck_verdict(xc),
            })

    from collections import Counter
    st, per_field = Counter(), {}
    for r in results:
        for row in r.get('fields', []):
            st[row['extract_status']] += 1
            per_field.setdefault(row['field_id'], Counter())[row['extract_status']] += 1
    errs = Counter(r.get('parse_error') for r in results if r.get('parse_error'))
    xstat = Counter(A03.xcheck_verdict(r.get('crosscheck', {})) for r in results)
    summary = {
        'slot': slot, 'tag': tag,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'documents': len(results), 'field_rows': n_fields,
        'status_counts': dict(st), 'crosscheck_docs': dict(xstat),
        'per_field': {k: dict(v) for k, v in per_field.items()},
        'parse_errors': {str(k): v for k, v in errs.items()},
        'avg_s_per_doc': round(sum(r.get('elapsed_s', 0) for r in results) / max(len(results), 1), 2),
    }
    json.dump(summary, io.open(jpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return fpath, n_fields, summary


def expected_docs(slot):
    rows = list(csv.DictReader(io.open(INDEX, encoding='utf-8-sig')))
    n = 0
    for r in rows:
        if r['slot_id'] != slot or r['status'] != 'COLLECTED_IDENTITY_VERIFIED':
            continue
        if (ROOT / r['local_file']).exists():
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slots', default='')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--tag', default='')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    slots = ALL_SLOTS if args.all else [s.strip() for s in args.slots.split(',') if s.strip()]
    if not slots:
        raise SystemExit('need --slots or --all')

    OUT.mkdir(parents=True, exist_ok=True)
    grand = {'slots': {}, 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    t_all = time.time()

    for slot in slots:
        suffix = f'_{args.tag}' if args.tag else ''
        jpath = OUT / f'{slot}{suffix}_summary.json'
        exp = expected_docs(slot)
        if jpath.exists() and not args.force:
            prev = json.load(io.open(jpath, encoding='utf-8'))
            if prev.get('documents', 0) >= exp and exp > 0:
                print(f'[S00] {slot}: skip (already {prev["documents"]}/{exp})', flush=True)
                grand['slots'][slot] = {'skipped': True, 'documents': prev['documents']}
                continue

        limit = None if (args.all or args.limit == 0) else args.limit
        tasks = A03.load_tasks([slot], limit)
        print(f'[S00] {slot}: tasks={len(tasks)} expected={exp} workers={args.workers}', flush=True)
        t0 = time.time()
        results = []
        if args.workers <= 1:
            for i, t in enumerate(tasks, 1):
                results.append(A03.extract_one(t))
                if i % 50 == 0:
                    print(f'  {slot} {i}/{len(tasks)} {time.time()-t0:.0f}s', flush=True)
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(A03.extract_one, t): t for t in tasks}
                done = 0
                for fu in as_completed(futs):
                    try:
                        results.append(fu.result())
                    except Exception as exc:  # noqa: BLE001
                        t = futs[fu]
                        results.append({**t, 'fields': [], 'parse_error': f'WORKER_FAILED: {exc}',
                                        'n_pages': 0, 'text_chars': 0, 'elapsed_s': 0})
                    done += 1
                    if done % 100 == 0:
                        print(f'  {slot} {done}/{len(tasks)} {time.time()-t0:.0f}s', flush=True)

        results.sort(key=lambda x: (x['slot_id'], x['security_id']))
        fpath, n_fields, summary = write_slot(slot, results, args.tag)
        print(f'[S00] {slot}: docs={len(results)} fields={n_fields} '
              f'elapsed={time.time()-t0:.0f}s -> {fpath.name}', flush=True)
        grand['slots'][slot] = {'skipped': False, 'documents': len(results),
                                'field_rows': n_fields,
                                'status_counts': summary['status_counts'],
                                'elapsed_s': round(time.time() - t0, 1)}

    grand['elapsed_s'] = round(time.time() - t_all, 1)
    if not args.tag:
        json.dump(grand, io.open(OUT / 'extract_run_summary.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in grand.items() if k != 'slots'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
