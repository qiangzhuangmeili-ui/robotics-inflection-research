"""换件后补 002415 / 002611 的 2026H1 与 Q3 单季：用 s00_normalize 真跑，不手搓元数据。

做法：把这两家的 h1_2026 抽取换成中文原版的新结果，其余输入沿用 v7/v8 基线，
只对这两家跑一次标准化，然后把 20260630 的全部行 + 20260630/20260930 的单季行合并进 s00_v8。
"""
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import s00_normalize as N          # noqa: E402
import a03_financial_field_extractor as A   # noqa: E402

TARGETS = [('SZ:002415', '002415'), ('SZ:002611', '002611')]
SLOTS = ['annual_2023', 'annual_2024', 'annual_2025',
         'h1_2024', 'h1_2025', 'h1_2026',
         'q1_2024', 'q1_2025', 'q1_2026',
         'q3_2024', 'q3_2025', 'q3_2026']


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig', newline='')))


def write(p, rows):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    # 1. 现场抽中文原版
    index = {}
    for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
        index[(r['security_id'], r['slot_id'])] = r
    fresh = {}
    for sec, code in TARGETS:
        rec = index[(sec, 'h1_2026')]
        res = A.extract_one(dict(document_id=rec['document_id'], security_id=sec, stock_code=code,
                                 slot_id='h1_2026', period_label='h1_2026',
                                 path=str(ROOT / rec['local_file'])))
        assert not res['parse_error'], res['parse_error']
        fresh[(sec, 'h1_2026')] = res
        hit = [f for f in res['fields'] if f['field_id'] == 'FIN.NPDEDT.YTD'
               and f['extract_status'] == 'EXTRACTED']
        print(f"{code} 中文版扣非 {hit[0]['value_raw'] if hit else 'MISSING'} page={hit[0]['page'] if hit else ''}")

    # 2. 组装抽取源：基线 CSV + 定向重抽 + 扣非覆盖 + 本次换件
    remed = {}
    for f in (ROOT / 'runs/issues/S02/remediation_20261029/extracted').glob('*.json'):
        j = json.loads(f.read_text(encoding='utf-8'))
        remed[(j['security_id'], j['slot_id'])] = j
    npd = json.loads((HERE / 'npdedt_override_rows.json').read_text(encoding='utf-8'))

    def load_extract(slot):
        out = defaultdict(dict)
        for r in csv.DictReader(open(ROOT / f'runs/issues/S00/extract/{slot}_fields.csv',
                                     encoding='utf-8-sig')):
            out[r['security_id']][(r['field_id'], r['note'])] = r
        for (sec, sl), r in remed.items():
            if sl == slot:
                out[sec] = {(f['field_id'], f['note']): f for f in r['fields']}
        for key, row in npd.items():
            sec, sl = key.split('|')
            if sl == slot:
                out[sec][(row['field_id'], row['note'])] = row
        for (sec, sl), res in fresh.items():
            if sl == slot:
                out[sec] = {(f['field_id'], f['note']): f for f in res['fields']}
        return out

    def load_diag(slot):
        out = {}
        for r in csv.DictReader(open(ROOT / f'runs/issues/S00/extract/{slot}_diag.csv',
                                     encoding='utf-8-sig')):
            out[r['security_id']] = r
        for (sec, sl), res in fresh.items():
            if sl == slot:
                d = dict(out.get(sec, {}))
                d.update({k: res.get(k, '') for k in ['parse_error', 'restatement',
                                                      'restatement_method', 'n_pages', 'text_chars']})
                xc = res.get('crosscheck', {})
                d['xcheck_pass'] = A.xcheck_verdict(xc)
                for f, k in [('FIN.REV.YTD', 'xcheck_rev'), ('FIN.NPP.YTD', 'xcheck_npp'),
                             ('FIN.OCF.YTD', 'xcheck_ocf')]:
                    d[k] = xc.get(f, '')
                out[sec] = d
        return out

    orig_companies = N.load_companies

    def two():
        d = orig_companies()
        keep = {s for s, _ in TARGETS}
        return {k: v for k, v in d.items() if k in keep}

    oldmanifest = json.loads((ROOT / 'runs/issues/S00/normalization_manifest.json')
                             .read_text(encoding='utf-8'))
    idx = N.load_index()
    old_lang = {str(ROOT / idx[(r['slot_id'], r['security_id'])]['local_file']):
                (r['language'], r.get('zh_ratio', 0), r.get('text_chars', 0))
                for r in oldmanifest.get('empty_slots_no_value', {}).get('items', [])
                if (r['slot_id'], r['security_id']) in idx}
    orig_lang = N.detect_doc_language

    N.detect_doc_language = lambda p, pages=3: old_lang.get(str(p)) or orig_lang(p, pages)
    N.load_extract, N.load_diag, N.load_companies = load_extract, load_diag, two
    N.OUT = HERE / '_replace_run'
    N.OUT.mkdir(exist_ok=True)
    N.main()

    # 3. 合并：这两家 20260630 全部行 + 20260630/20260930 单季行
    with gzip.open(HERE / 's00_v8.csv.gz', 'rt', encoding='utf-8-sig', newline='') as f:
        base = list(csv.DictReader(f))
    header = list(base[0].keys())
    got = read(N.OUT / 'financial_normalized.csv')
    keep = {s for s, _ in TARGETS}
    add = [r for r in got
           if r['security_id'] in keep
           and (r['period_key'] == '20260630'
                or (r['period_key'] in ('20260630', '20260930') and r['field_id'].endswith('.SQ')))]
    idx0 = {(r['security_id'], r['period_key'], r['field_id']): r for r in base}
    added, replaced = [], []
    for r in add:
        k = (r['security_id'], r['period_key'], r['field_id'])
        if k in idx0:
            if idx0[k] != r:
                replaced.append(dict(security_id=k[0], period_key=k[1], field_id=k[2],
                                     old=idx0[k].get('value_cny'), new=r.get('value_cny')))
                idx0[k].update(r)
        else:
            base.append(r)
            idx0[k] = r
            added.append(dict(security_id=k[0], period_key=k[1], field_id=k[2],
                              value=r.get('value_cny'), status=r.get('status')))
    out = HERE / 's00_v9.csv'
    write(out, base)
    with (HERE / 's00_v9.csv.gz').open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as g:
            g.write(out.read_bytes())
    summary = dict(rows=len(base), added=len(added), replaced=len(replaced),
                   added_by_field=dict((f, sum(1 for a in added if a['field_id'] == f))
                                       for f in sorted({a['field_id'] for a in added})),
                   detail_added=added, detail_replaced=replaced)
    (HERE / 's00_v9_patch_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if not k.startswith('detail')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
