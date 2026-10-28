"""S00 收口：更新 active_issue、执行计划表、PROJECT_STATE。"""
import csv
import io
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = time.strftime('%Y-%m-%dT%H:%M:%S+08:00')

# 1) active_issue.json
p = ROOT / 'data/active_issue.json'
d = json.load(io.open(p, encoding='utf-8'))
d['active_issue_number'] = None
d['active_issue_key'] = None
d['executor'] = None
d['status'] = 'IDLE_S00_SELF_CHECK_PASS_S01_READY'
d['claim_note'] = ('S00 完成：全池 12 槽重抽 + 旧快照 2021/2022，228,154 行逐格可复算；'
                   '1054 家全在、缺失不填 0、62 个整槽无值已定性并交接；放行 S01。')
d['last_completed'] = {
    'issue_number': 35,
    'issue_key': 'S00',
    'completed_at': NOW,
    'review_file': 'runs/issues/S00/review.json',
    'decision': 'SELF_CHECK_PASS',
    'acceptance': '2/2',
    'summary': ('228,154 行标准化财务；1054 家 / 12,648 槽全覆盖；'
                'V1 四季和 10,745 通过；V3 PDF vs 快照 16,921/17,363 一致；'
                '单季官方分季表 40,264 格；62 个整槽无值（英文版 26 / 无文本层 14 / 抽取盲区 20 / 混排 2）'),
}
d['next_recommended_issue_number'] = 36
d['next_recommended_issue_key'] = 'S01'
d['next_recommended_reason'] = (
    'S00 已放行：标准化财务表可用，S01 可登记筛选公式/阈值/缺失与亏损规则；'
    '仍不得跳业务深研或估值。')
d['open_followups_from_s00'] = [
    '62 个整槽无值：英文版 26（F32 采集器未校验语言）、无文本层 14、抽取盲区 20、混排 2。',
    '453 份文档三表与摘要表不一致（1,326 格标 EXTRACTED_XCHECK_MISMATCH），S02 用前须核或排除。',
    '2,157 份重述标记为 NEEDS_REVIEW（关键词判据，未逐份确认勾选项）。',
    '旧快照 2021/2022 为单一来源，无官方 PDF 交叉校验。',
    '未用最新年报「上年同期」列重算历史期，重述公司跨年口径可能不一致。',
    '2026Q3 仅 190 家已披露，其余 864 家未到披露期（NOT_YET_DISCLOSED），当期截面不完整。',
]
json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# 2) issue_execution_plan.csv
p = ROOT / 'data/issue_execution_plan.csv'
rows = list(csv.DictReader(io.open(p, encoding='utf-8-sig')))
fields = list(rows[0].keys())
for r in rows:
    if r['key'] == 'S00':
        r['status'] = 'SELF_CHECK_PASS'
    elif r['key'] == 'S01':
        r['status'] = 'READY'
with io.open(p, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

# 3) PROJECT_STATE.json
p = ROOT / 'PROJECT_STATE.json'
st = json.load(io.open(p, encoding='utf-8'))
st['status'] = 'S00_SELF_CHECK_PASS_S01_READY'
st['s00_stage'] = {
    'issue': 'S00 / #35',
    'decision': 'SELF_CHECK_PASS',
    'review_nature': 'SELF_CHECK',
    'completed_at': NOW,
    'documents_extracted': 11468,
    'field_rows_extracted': 213446,
    'normalized_rows': 228154,
    'companies': 1054,
    'slots_total': 12648,
    'slots_with_value': 11406,
    'empty_slots': 62,
    'empty_slots_breakdown': {'EN_OR_NON_ZH': 26, 'NO_TEXT_LAYER': 14, 'ZH': 20, 'MIXED': 2},
    'issues_rows': 14350,
    'checks': {
        'V1_four_quarter_sum_pass': 10745,
        'V1_mismatch': 114,
        'V1_arbitration': {'quarterly_sum_adopted': 64, 'ytd_kept': 24,
                           'both_far': 3, 'unresolved': 23},
        'V3_pdf_vs_provider': {'match': 16921, 'mismatch': 442},
        'V4_gross_margin': {'match': 3334, 'minor_le_2pp': 381, 'mismatch_gt_2pp': 59},
        'three_statement_vs_key_table': {'match': 10542, 'partial': 242,
                                         'no_key_table': 231, 'mismatch': 453},
    },
    'single_quarter_sources': {'official_quarterly_table': 40264, 'q1_equals_ytd': 5372,
                               'derived_cumulative_diff': 8603, 'cross_source_blocked': 27},
    'new_defects': ['F28', 'F29', 'F30', 'F31 已修', 'F32 未修（英文版年报）'],
    'release_next': 'S01',
    'limits': ['旧快照 2021/2022 单一来源', '未用最新年报重算历史期',
               '453 份 xcheck 不一致', '2026Q3 仅 190 家已披露'],
}
st['next_issue'] = {'key': 'S01', 'number': 36,
                    'reason': 'S00 放行；S01 只登记规则版本，不看个别公司调阈值'}
json.dump(st, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('state files updated')
