"""收口：更新 v8 计算清单（计数/指纹/已知限制）、review 结论与总汇总。"""
import csv
import hashlib
import json
import collections
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
OUT = Path(__file__).parent


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig')))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rel(p):
    return str(Path(p).relative_to(ROOT)).replace(chr(92), '/')


def main():
    m = read(OUT / 's02_v8/all_pool_metrics.csv')
    c = read(OUT / 's02_v8/company_metric_summary.csv')
    md = read(OUT / 'metric_delta_v7_v8.csv')
    counts = dict(cells=len(m))
    for k, v in collections.Counter(r['metric_status'] for r in m).items():
        counts[k.lower()] = v

    mp = OUT / 's02_v8/calculation_manifest.json'
    man = json.loads(mp.read_text(encoding='utf-8'))
    man['executor'] = 'WorkBuddy AI'
    man['input_version'] = 'S00_M07_NPDEDT_REPAIR_V8_20261030'
    man['counts'] = counts
    man['l0_distribution'] = dict(collections.Counter(r['l0_evaluability'] for r in c))
    for o in man['outputs']:
        p = OUT / 's02_v8' / Path(o['path']).name
        o.update(path=rel(p), sha256=sha(p), bytes=p.stat().st_size)
    man['known_limits'] = [x for x in man['known_limits']
                           if not x.startswith(('S00 遗留：62', '上游缺陷一'))]
    man['known_limits'] += [
        'S00 遗留：62 整槽无值、三表≠摘要表 453 份（HOLD 176 格，本轮未处理）',
        '上游缺陷一：53 家最新期可用字段<8，A03 字段抽取只覆盖年报，须回 S00 补抽半年报/季报字段',
        '本轮只补扣非累计：000856 冀东装备 Q1 为图片版、002415 海康威视与 002611 东方精工 H1 为英文版，'
        '三家 M07 仍 MISSING',
        '本轮未重跑全池抽取：当前 HEAD 解析器与 S00 时期版本存在漂移（部分科创板季报利润表归母取不到），'
        '全池重抽会丢值，须单独立项',
    ]
    mp.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding='utf-8')

    rv = OUT / 's02_v8/review.json'
    v = json.loads(rv.read_text(encoding='utf-8'))
    v.update(executor='WorkBuddy AI', reviewer='WorkBuddy AI',
             decision='SELF_CHECK_PASS_M07_REPAIR_EXTERNAL_REVIEW_REQUIRED',
             limits=man['known_limits'], next_stage_release='S03_LOCKED')
    rv.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding='utf-8')

    summary = dict(
        parser_sha256=sha(ROOT / 'tools/a03_financial_field_extractor.py'),
        npdedt_added=74, sq_added=126,
        metric_changes=len(md),
        metric_companies=len({r['security_id'] for r in md}),
        by_metric=dict(collections.Counter(r['metric_id'] for r in md)),
        by_status=dict(collections.Counter(r['metric_status'] for r in md)),
        status_counts=counts,
        l0_counts=man['l0_distribution'],
        m07=dict(collections.Counter(r['metric_status'] for r in m if r['metric_id'] == 'M07')),
        m07_missing_list=[f"{r['stock_code']} {r['stock_name']}"
                          for r in m if r['metric_id'] == 'M07' and r['metric_status'] == 'MISSING'],
    )
    (OUT / 'rebuild_v8_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
