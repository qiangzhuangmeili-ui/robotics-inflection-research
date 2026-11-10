import json, hashlib, copy
from pathlib import Path

v2p = Path('runs/issues/S01/screen_rules_v2.json')
v2 = json.loads(v2p.read_text(encoding='utf-8'))
v2sha = hashlib.sha256(v2p.read_bytes()).hexdigest()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


v3 = copy.deepcopy(v2)
v3['rules_version'] = 'S01_SCREEN_RULES_V3'
v3['created_at'] = '2026-11-10T20:45:00+08:00'
v3['frozen_at'] = '2026-11-10T20:45:00+08:00'
v3['freeze_order'] = 'S04_REWORK_20261110'
v3['status'] = 'FROZEN'
v3['purpose'] = v2['purpose'] + '｜V3：L2 改为双通道资格判定，并补齐低基数绝对额确认口径（S04 返工）。'

for layer in v3['decision_layers']:
    if layer['id'] == 'L2':
        layer['rule_text'] = (
            '在 GROWTH / MARGIN / PROFIT / CASH 四个维度中，至少 2 个不同维度各有 1 条合格真信号；'
            '比率通道所用指标须全部 metric_status=OK；SG06/SG08 绝对额通道须全部实际输入行 status 属 '
            'status_semantics.usable 且跨期可比；两类通道均不得含 Q01 HOLD、Q06 未决重述、'
            '范围断裂（SCOPE_CHANGE / STRUCTURAL_BREAK）或 Q05 低基数未确认'
        )
        layer['channel_qualification'] = {
            'ratio_channel': {
                'signals': ['SG01', 'SG02', 'SG03', 'SG04', 'SG05', 'SG07', 'SG09'],
                'requirement': '所用指标 metric_status 必须为 OK',
            },
            'absolute_channel': {
                'signals': ['SG06', 'SG08'],
                'requirement': ('实际输入行 status 属 status_semantics.usable 且两侧跨期可比；'
                                '不因比率型指标 UNDEFINED_BASE 而失效；须单独登记 ABS_CHANNEL 资格，'
                                '不得直接沿用上游 CLEAN 标签放行'),
            },
            'rationale': ('SG06 的 metric M05 在基期<0 时必为 UNDEFINED_BASE。若强制 OK，SG06 在 L2 永久失效，'
                          '与 policies.loss「亏损公司不计算同比比率，改判绝对额改善或转正」直接冲突。'),
        }
        layer['low_base_policy'] = '低基数信号须按 low_base_confirmation 的同口径绝对额确认（增量≥1,000 万元）才计入维度'
    if layer['id'] == 'L3':
        layer['rule_text'] = layer['rule_text'] + '；绝对额通道信号另须登记 ABS_CHANNEL 资格与输入行 document_id'

v3['low_base_confirmation'] = {
    'threshold_cny': 10000000,
    'direction': 'SAME_DIRECTION',
    'basis_rule': '确认金额必须与信号自身口径一致：累计信号用累计绝对额，单季信号用单季绝对额',
    'signals': {
        'SG01': {'field_id': 'FIN.REV.YTD', 'basis': 'YTD'},
        'SG04': {'field_id': 'FIN.NPDEDT.YTD', 'basis': 'YTD'},
        'SG06': {'field_id': 'FIN.NPDEDT.YTD', 'basis': 'YTD',
                 'extra': '当期金额仍须满足本信号 threshold（1,000 万元）'},
        'SG08': {'field_id': 'FIN.OCF.YTD', 'basis': 'YTD'},
        'SG09': {'field_id': 'FIN.NPDEDT.SQ', 'basis': 'SQ'},
    },
    'no_confirm_rule': ['SG02', 'SG03', 'SG05', 'SG07'],
    'no_confirm_rule_handling': '记 NO_CONFIRM_RULE，保留观察队列，本版不计入维度；不得以任意金额替代；如需启用须另立版本预登记映射',
    'no_confirm_input_handling': '有映射但两侧输入行缺失或不可用时记 NO_CONFIRM_INPUT',
    'input_requirement': ('两侧行 status 属 status_semantics.usable，且 restatement_flag 不为 '
                          'RESTATEMENT_INDICATED_NEEDS_REVIEW（Q06 未决重述不得确认）'),
    'comparability_requirement': '两侧 period_key 为同一会计期间的上年同期；跨年、跨版本、跨合并范围不得相减',
}

v3['policies']['low_base']['actions'] = [
    '基期营收<5,000 万元 或 |基期扣非|<1,000 万元 或 low_base_flag=YES',
    'L1 可进观察队列但标 PROVISIONAL',
    'L2 需按 low_base_confirmation 的同口径绝对额同向确认（增量≥1,000 万元）',
    '无确认映射的信号记 NO_CONFIRM_RULE，本版不计入 L2 维度',
]

v3['input_fingerprint'] = {
    'files': [
        {'path': 'runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz',
         'sha256': sha('runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz'),
         'bytes': Path('runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz').stat().st_size,
         'role': 'AUTHORITATIVE_NORMALIZED'},
        {'path': 'runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv',
         'sha256': sha('runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv'),
         'bytes': Path('runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv').stat().st_size,
         'role': 'METRICS'},
        {'path': 'data/company_master.csv',
         'sha256': sha('data/company_master.csv'),
         'bytes': Path('data/company_master.csv').stat().st_size,
         'role': 'MASTER'},
    ],
    'superseded': [
        {'path': 'runs/issues/S00/financial_normalized.csv',
         'note': ('S00 交付件，228,155 行，已被 s00_v10 取代：240 格数值不同、仅新版有 1,784 键；'
                  '下游复算一律不得读取，仅作历史快照')},
    ],
    'note': ('V3 起指纹改指向 S02 已验收的 s00_v10（sha 与 S03 输入契约 normalized.sha256 一致）。'
             '旧 S00 交付件保留但禁止用于任何复算。'),
}

v3['change_log'] = v2['change_log'] + [{
    'from_version': 'S01_SCREEN_RULES_V2',
    'from_sha256': v2sha,
    'from_frozen_at': v2.get('frozen_at'),
    'reason': ('S04 独立复核两项 P1：①P1-02 L2 原文「所用指标均 metric_status=OK」与 policies.loss '
               '「亏损公司改判绝对额改善或转正」冲突——SG06 只在基期<0 时触发，此时 M05 必为 '
               'UNDEFINED_BASE，严格按原文将使 SG06 在 L2 永久失效；②P1-01 低基数绝对额确认只有散文条款、'
               '无口径定义，S04 无法执行。另修正输入指纹指向被取代的旧 S00。'),
    'changes': [
        'decision_layers[L2].rule_text：改为双通道资格判定',
        'decision_layers[L2].channel_qualification：新增比率通道/绝对额通道资格定义',
        'low_base_confirmation：新增低基数同口径绝对额确认映射（SG01/SG04/SG06/SG08/SG09）',
        'low_base_confirmation.no_confirm_rule：SG02/SG03/SG05/SG07 记 NO_CONFIRM_RULE',
        'policies.low_base.actions：指向 low_base_confirmation',
        'input_fingerprint：改指向 s00_v10，旧 S00 列入 superseded',
    ],
    'not_a_research_decision': ('SG01-SG09 全部 threshold 一字未改；未按命中率或目标家数调整；'
                                '未把 M05 的 UNDEFINED_BASE 改写为 OK；未新增或删除任何信号'),
    'recompute': '全池 1054 家重算，v2/v3 差异与逐家口径变化记录在 runs/issues/S04/rework_20261110/',
    'approved_by': 'User（2026-11-10 授权按 Codex 裁决返工）',
    'advisor_ruling': 'runs/issues/S04/codex_ruling.md',
}]

out = Path('runs/issues/S01/screen_rules_v3.json')
out.write_text(json.dumps(v3, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('written:', out)
print('v3 sha256:', sha(out))
print('thresholds:', {s['id']: s['threshold'] for s in v3['signals']})
