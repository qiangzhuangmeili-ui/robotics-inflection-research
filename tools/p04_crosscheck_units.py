"""P04 证据采集 C：同公司同报告期，第三方结构化接口与官方 PDF 的数值/单位一致性核对。

用途：证明 provider_field_mapping 中"数值口径=元、报告期=累计"不是猜的，而是两边逐项对得上；
同时暴露接口缺字段（如扣非）与口径差（如单季度）。

只做数值比对，不做财务分析、不改任何原件。
"""
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
URL = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'

# (security_id, 报告期键, document_id, 期间标签)
PAIRS = [
    ('SH:688218', '20251231', 'DOC-055EAAF729BDBA32', 'FY2025'),
    ('BJ:920207', '20260630', 'DOC-2026H1-920207', '2026H1'),
]
# 目标字段 -> (新浪 item_field, 新浪所在表)
FIELD_MAP = {
    '营业收入': ('BIZINCO', 'lrb'),
    '营业成本': ('BIZCOST', 'lrb'),
    '归属于母公司所有者的净利润': ('PARENETP', 'lrb'),
    '经营活动产生的现金流量净额': ('MANANETR', 'llb'),
    '应收账款': ('ACCORECE', 'fzb'),
    '存货': ('INVE', 'fzb'),
    '合同资产': ('CONTRACTASSET', 'fzb'),
}
MONEY = re.compile(r'-?\d{1,3}(?:,\d{3})+\.\d{2}|-?\d+\.\d{2}')


def to_float(text):
    return float(str(text).replace(',', ''))


def fetch(session, security_id, source, num=8):
    exchange, code = security_id.split(':')
    params = {'paperCode': exchange.lower() + code, 'source': source, 'type': '0', 'page': '1', 'num': str(num)}
    resp = session.get(URL, params=params, timeout=(8, 20))
    resp.raise_for_status()
    data = resp.json()['result']['data']
    return data.get('report_list') or {}, params, len(resp.content)


def pdf_values(document_id, period):
    path = OUT / 'pdf_lineitem_evidence.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    values = {}
    for row in doc['line_items']:
        if row['document_id'] != document_id or row.get('period') != period:
            continue
        if row['statement'] in ('BS', 'IS', 'CF') and row.get('values_found'):
            values[row['target']] = row['values_found'][0]
    for row in doc['line_items']:
        if row['document_id'] != document_id or row.get('period') != period:
            continue
        if row['statement'] == 'KEY_FINANCIALS' and row.get('raw_line'):
            block = row['raw_line']
            for label, key in (('营业收入', '营业收入'), ('归属于上市公司股东的净利润', '归属于母公司所有者的净利润')):
                idx = block.find(label)
                if idx >= 0 and key not in values:
                    m = MONEY.search(block[idx + len(label):])
                    if m:
                        values[key] = m.group(0)
    return values


def main():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})
    results = []
    for security_id, period_key, document_id, period_label in PAIRS:
        cache = {}
        for source in ('lrb', 'fzb', 'llb'):
            report_list, params, size = fetch(session, security_id, source)
            cache[source] = {'report_list': report_list, 'params': params, 'size_bytes': size}
        pdfv = pdf_values(document_id, period_label)
        for field, (item_field, source) in FIELD_MAP.items():
            block = cache[source]['report_list'].get(period_key)
            provider_value = None
            if block:
                for item in block.get('data') or []:
                    if item.get('item_field') == item_field:
                        provider_value = item.get('item_value')
                        break
            pdf_raw = pdfv.get(field)
            row = {
                'security_id': security_id, 'period_key': period_key, 'period_label': period_label,
                'document_id': document_id, 'field_cn': field, 'provider': 'SINA_NON_OFFICIAL',
                'provider_item_field': item_field, 'provider_value': provider_value,
                'provider_currency': (block or {}).get('rCurrency'),
                'provider_publish_date': (block or {}).get('publish_date'),
                'official_pdf_value_raw': pdf_raw,
            }
            if provider_value not in (None, '') and pdf_raw not in (None, ''):
                diff = abs(to_float(provider_value) - to_float(pdf_raw))
                row['abs_diff_cny'] = round(diff, 2)
                row['verdict'] = 'MATCH_EXACT' if diff < 0.005 else ('MISMATCH' if diff > 1 else 'MATCH_ROUNDING')
            elif provider_value in (None, '') and pdf_raw not in (None, ''):
                row['verdict'] = 'PROVIDER_FIELD_MISSING'
            elif provider_value not in (None, '') and pdf_raw in (None, ''):
                row['verdict'] = 'PDF_LABEL_NOT_EXTRACTED'
            else:
                row['verdict'] = 'BOTH_MISSING'
            results.append(row)
    summary = {}
    for row in results:
        summary[row['verdict']] = summary.get(row['verdict'], 0) + 1
    payload = {
        'checked_at': None,
        'method': '同公司同报告期：新浪结构化接口(type=0 累计) vs 官方年报PDF合并报表行项目，逐项比对绝对差',
        'pairs': [{'security_id': p[0], 'period_key': p[1], 'document_id': p[2], 'period_label': p[3]} for p in PAIRS],
        'verdict_counts': summary,
        'rows': results,
        'limitations': [
            '只比对2家公司2个报告期，不等于全池口径验收',
            '新浪为非官方结构化数据，官方PDF为年报正文；两者一致只证明数值与单位对齐，不证明业务口径正确',
            'PDF数值由文本抽取得到，可能存在折行/列错位，已保留原始行文本供复核',
        ],
    }
    (OUT / 'crosscheck_provider_vs_pdf.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'verdict_counts': summary, 'rows': len(results)}, ensure_ascii=False))
    for r in results:
        if r['verdict'] != 'MATCH_EXACT':
            print('  ', r['security_id'], r['field_cn'], r['provider_value'], r['official_pdf_value_raw'], r['verdict'])


if __name__ == '__main__':
    sys.exit(main())
