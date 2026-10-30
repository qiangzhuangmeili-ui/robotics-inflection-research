"""对齐并表 HOLD 覆盖行（与 v7_guarded 逐列一致），重算指标差异表。"""
import csv
import collections
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
OUT = Path(__file__).parent
V7P = ROOT / 'runs/issues/S02/remediation_20261029/collect_q3_2026/s02_v7_guarded/all_pool_metrics.csv'
COLS = ('metric_status', 'quality_flags', 'evaluable', 'note', 'input_found', 'input_missing',
        'source_refs')


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig')))


def write(p, rows):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    v7 = {(r['security_id'], r['metric_id']): r for r in read(V7P)}
    m = read(OUT / 's02_v8/all_pool_metrics.csv')
    fixed = 0
    for r in m:
        a = v7[(r['security_id'], r['metric_id'])]
        if a['quality_flags'] == 'Q01_SCOPE_CHANGE':
            for col in COLS:
                if r[col] != a[col]:
                    r[col] = a[col]
                    fixed += 1
    write(OUT / 's02_v8/all_pool_metrics.csv', m)
    md = [r for r in m if r != v7[(r['security_id'], r['metric_id'])]]
    write(OUT / 'metric_delta_v7_v8.csv', md)
    print('fixed fields', fixed, 'delta rows', len(md))
    print(dict(collections.Counter(r['metric_id'] for r in md)))
    print(dict(collections.Counter(f"{v7[(r['security_id'], r['metric_id'])]['metric_status']}"
                                   f"->{r['metric_status']}" for r in md)))


if __name__ == '__main__':
    main()
