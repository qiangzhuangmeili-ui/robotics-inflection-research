"""v9 收口：对齐并表 HOLD 覆盖行、重算差异表、更新计算清单与汇总。"""
import collections
import csv
import hashlib
import json
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


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    v7 = {(r['security_id'], r['metric_id']): r for r in read(V7P)}
    m = read(OUT / 's02_v9/all_pool_metrics.csv')
    fixed = 0
    for r in m:
        a = v7[(r['security_id'], r['metric_id'])]
        if a['quality_flags'] == 'Q01_SCOPE_CHANGE':
            for col in COLS:
                if r[col] != a[col]:
                    r[col] = a[col]
                    fixed += 1
    write(OUT / 's02_v9/all_pool_metrics.csv', m)
    md = [r for r in m if r != v7[(r['security_id'], r['metric_id'])]]
    write(OUT / 'metric_delta_v7_v9.csv', md)

    c = read(OUT / 's02_v9/company_metric_summary.csv')
    counts = dict(cells=len(m))
    for k, v in collections.Counter(r['metric_status'] for r in m).items():
        counts[k.lower()] = v

    mp = OUT / 's02_v9/calculation_manifest.json'
    man = json.loads(mp.read_text(encoding='utf-8'))
    man['executor'] = 'WorkBuddy AI'
    man['input_version'] = 'S00_M07_CN_H1_REPAIR_V9_20261030'
    man['counts'] = counts
    man['l0_distribution'] = dict(collections.Counter(r['l0_evaluability'] for r in c))
    for o in man['outputs']:
        p = OUT / 's02_v9' / Path(o['path']).name
        o.update(path=str(p.relative_to(ROOT)).replace(chr(92), '/'), sha256=sha(p),
                 bytes=p.stat().st_size)
    man['known_limits'] = [x for x in man['known_limits']
                           if not x.startswith(('S00 遗留：62', '上游缺陷一', '本轮只补扣非累计'))]
    man['known_limits'] += [
        'S00 遗留：62 整槽无值、三表≠摘要表 453 份（HOLD 176 格，本轮未处理）',
        '上游缺陷一：53 家最新期可用字段<8，A03 字段抽取只覆盖年报，须回 S00 补抽半年报/季报字段',
        '本轮扣非缺口已清零；000856 2026Q1 为图片版，扣非按 OCR+原页核对采用（见 OCR_ADOPTION_000856.md）',
        '002415/002611 的 2026 半年报已由英文版换成巨潮中文原版（文档身份不变，旧英文件留档）',
        '本轮未重跑全池抽取：当前 HEAD 解析器与 S00 时期版本存在漂移（部分科创板季报利润表归母取不到），'
        '全池重抽会丢值，须单独立项',
    ]
    mp.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding='utf-8')

    rv = OUT / 's02_v9/review.json'
    v = json.loads(rv.read_text(encoding='utf-8'))
    v.update(executor='WorkBuddy AI', reviewer='WorkBuddy AI',
             decision='SELF_CHECK_PASS_M07_ZERO_GAP_EXTERNAL_REVIEW_REQUIRED',
             limits=man['known_limits'], next_stage_release='S03_LOCKED')
    rv.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding='utf-8')

    summary = dict(
        metric_changes=len(md),
        metric_companies=len({r['security_id'] for r in md}),
        by_metric=dict(collections.Counter(r['metric_id'] for r in md)),
        by_status=dict(collections.Counter(r['metric_status'] for r in md)),
        status_counts=counts,
        l0_counts=man['l0_distribution'],
        m07=dict(collections.Counter(r['metric_status'] for r in m if r['metric_id'] == 'M07')),
        scope_guard_rows=fixed,
    )
    (OUT / 'rebuild_v9_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
