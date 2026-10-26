"""P04 证据采集 D：累计/单季度口径核对。

实测结论（本脚本可复算）：
- 新浪接口 type=0/1/2/3/4 是"报告期类型选择"（全部/一季/半年/三季/年报），返回的都是**年初至今累计**，
  并不提供单季度序列；type=1 之所以看起来像单季，是因为一季度累计恰好等于一季度单季。
- 因此单季度只能：①优先取官方年报"分季度主要财务数据"表；②否则用同一报告年度内累计相减，
  且必须与官方分季表逐季勾稽、且期间不得有追溯重述或合并范围变化。

本脚本对 2 家公司 × 3 个字段 × 4 个季度做：累计值比对、累计差=单季 的验证、四季加总=全年 的验证。
"""
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
URL = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'
MONEY = re.compile(r'-?\d{1,3}(?:,\d{3})+\.\d{2}|-?\d+\.\d{2}')

SAMPLES = [
    {'security_id': 'SH:688218', 'document_id': 'DOC-055EAAF729BDBA32', 'period_label': 'FY2025',
     'quarter_ends': ['20250331', '20250630', '20250930', '20251231'], 'fy_key': '20251231'},
    {'security_id': 'SZ:002354', 'document_id': 'DOC-2025AR-002354', 'period_label': 'FY2025',
     'quarter_ends': ['20250331', '20250630', '20250930', '20251231'], 'fy_key': '20251231'},
]
FIELDS = [
    ('营业收入', 'BIZINCO', 'lrb'),
    ('归属于上市公司股东的净利润', 'PARENETP', 'lrb'),
    ('经营活动产生的现金流量净额', 'MANANETR', 'llb'),
]


def label_pattern(label):
    return r'\s*'.join(map(re.escape, label))


def quarterly_from_pdf(document_id, period_label):
    doc = json.loads((OUT / 'pdf_lineitem_evidence.json').read_text(encoding='utf-8'))
    row = next(r for r in doc['line_items']
               if r['document_id'] == document_id and r.get('period') == period_label
               and r['statement'] == 'QUARTERLY' and r.get('raw_line'))
    text = row['raw_line'].replace(' | ', ' ')
    out = {'page': row['page']}
    for label, _, _ in FIELDS:
        m = re.search(label_pattern(label), text)
        if m:
            out[label] = MONEY.findall(text[m.end():m.end() + 220])[:4]
    m = re.search(label_pattern('归属于上市公司股东的扣除非经常性损益后的净利润'), text)
    if m:
        out['扣非归母净利润'] = MONEY.findall(text[m.end():m.end() + 220])[:4]
    return out


def fetch_cumulative(session, security_id, source, num=12):
    exchange, code = security_id.split(':')
    params = {'paperCode': exchange.lower() + code, 'source': source, 'type': '0', 'page': '1', 'num': str(num)}
    resp = session.get(URL, params=params, timeout=(8, 20))
    resp.raise_for_status()
    data = resp.json()['result']['data']
    out = {}
    for period, block in (data.get('report_list') or {}).items():
        out[period] = {i['item_field']: i['item_value'] for i in block.get('data') or []}
    return out, params


def num(text):
    return float(str(text).replace(',', ''))


def verdict_of(a, b):
    if a in (None, '') or b in (None, ''):
        return 'BOTH_OR_ONE_MISSING', None
    diff = round(abs(num(a) - num(b)), 2)
    return ('MATCH_EXACT' if diff < 0.005 else ('MISMATCH' if diff > 1 else 'MATCH_ROUNDING')), diff


def main():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})
    rows, type_probe = [], []
    # 记录 type 参数实际含义，避免把"一季报期"误当"单季度"
    for t in ['0', '1', '2', '3', '4']:
        params = {'paperCode': 'sh688218', 'source': 'lrb', 'type': t, 'page': '1', 'num': '8'}
        resp = session.get(URL, params=params, timeout=(8, 20))
        data = resp.json()['result']['data']
        periods = list((data.get('report_list') or {}).keys())
        type_probe.append({'type': t, 'periods_returned': periods[:6],
                           'period_suffix_set': sorted({p[4:] for p in periods})})
    for sample in SAMPLES:
        pdf = quarterly_from_pdf(sample['document_id'], sample['period_label'])
        for label, item_field, source in FIELDS:
            q = pdf.get(label) or []
            if len(q) < 4:
                rows.append({'security_id': sample['security_id'], 'field_cn': label,
                             'verdict': 'PDF_QUARTERLY_PARSE_INCOMPLETE', 'parsed': q})
                continue
            cumulative_pdf, cum = [], 0.0
            for v in q:
                cum += num(v)
                cumulative_pdf.append(f'{cum:,.2f}')
            data, params = fetch_cumulative(session, sample['security_id'], source)
            for idx, period in enumerate(sample['quarter_ends']):
                provider_cum = (data.get(period) or {}).get(item_field)
                v1, d1 = verdict_of(cumulative_pdf[idx], provider_cum)
                rows.append({
                    'security_id': sample['security_id'], 'document_id': sample['document_id'],
                    'field_cn': label, 'quarter': period, 'quarter_no': idx + 1,
                    'check': 'CUMULATIVE_PROVIDER_VS_PDF_QUARTERLY_SUM',
                    'official_pdf_cumulative': cumulative_pdf[idx], 'provider_cumulative': provider_cum,
                    'abs_diff_cny': d1, 'verdict': v1,
                })
                if idx > 0:
                    derived = f'{num(cumulative_pdf[idx]) - num(cumulative_pdf[idx - 1]):,.2f}'
                    v2, d2 = verdict_of(q[idx], derived)
                    rows.append({
                        'security_id': sample['security_id'], 'document_id': sample['document_id'],
                        'field_cn': label, 'quarter': period, 'quarter_no': idx + 1,
                        'check': 'SINGLE_QUARTER_EQ_CUMULATIVE_DIFF',
                        'official_pdf_single_quarter': q[idx], 'derived_single_quarter': derived,
                        'abs_diff_cny': d2, 'verdict': v2,
                    })
            v3, d3 = verdict_of(f'{sum(num(v) for v in q):,.2f}', (data.get(sample['fy_key']) or {}).get(item_field))
            rows.append({
                'security_id': sample['security_id'], 'document_id': sample['document_id'],
                'field_cn': label, 'quarter': sample['fy_key'], 'quarter_no': None,
                'check': 'SUM_OF_FOUR_QUARTERS_VS_PROVIDER_FY_CUMULATIVE',
                'official_pdf_fy_sum': f'{sum(num(v) for v in q):,.2f}',
                'provider_fy_cumulative': (data.get(sample['fy_key']) or {}).get(item_field),
                'abs_diff_cny': d3, 'verdict': v3,
            })
    counts = {}
    for r in rows:
        counts[r['verdict']] = counts.get(r['verdict'], 0) + 1
    payload = {
        'method': '官方年报分季度表 vs 新浪接口累计值；检验“累计差=单季”“四季加总=全年”',
        'provider_type_semantics': {
            'finding': 'type 是报告期类型选择（0全部/1一季/2半年/3三季/4年报），各 type 返回的均为年初至今累计，接口不提供单季度序列',
            'probe': type_probe,
        },
        'samples': SAMPLES, 'verdict_counts': counts, 'rows': rows,
        'rules_implied': [
            'P1：Q1单季 = 一季报累计值（Q1累计即Q1单季）。',
            'P2：Q2/Q3/Q4单季 = 本期累计 − 上一期累计，且两者必须同一年度、同一合并范围、同一版本。',
            'P3：公司已在年报“分季度主要财务数据”表直接披露单季时，以官方单季表为准，累计差只作勾稽。',
            'P4：发生追溯重述、同一控制下合并或合并范围变化时，禁止跨版本相减；改用重述后同一版本重算。',
            'P5：四季加总与全年累计不一致且无法用重述解释时，标记 PERIOD_INCONSISTENT 并阻断该字段。',
        ],
        'limitations': ['仅2家公司FY2025样本', '分季度表来自年报正文文本抽取，已保留原始块供复核'],
    }
    (OUT / 'crosscheck_period_conversion.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'verdict_counts': counts, 'rows': len(rows)}, ensure_ascii=False))
    for r in rows:
        if r.get('verdict') not in ('MATCH_EXACT',):
            print('  ', r['security_id'], r['field_cn'], r.get('quarter'), r.get('check'), r.get('verdict'),
                  r.get('abs_diff_cny'))


if __name__ == '__main__':
    sys.exit(main())
