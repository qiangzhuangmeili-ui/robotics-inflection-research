"""P04 证据采集 A：新浪财务接口三张表的真实字段名与空值形态。

只取 3 家已知样本、每张表 1 个报告期，用于冻结字段映射；不采全池、不做财务判断。
原始响应落 sources/p04_probe/（仓库忽略），摘要落 runs/issues/P04/。
"""
import csv, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
RAW = ROOT / 'sources/p04_probe'
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

SAMPLES = [('SH', '688218', '江苏北人'), ('SZ', '002031', '巨轮智能'), ('BJ', '920207', '众诚科技')]
STATEMENTS = [('lrb', '合并利润表'), ('fzb', '合并资产负债表'), ('llb', '合并现金流量表')]
URL = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'


def probe(session, exchange, code, source):
    params = {'paperCode': exchange.lower() + code, 'source': source, 'type': '0', 'page': '1', 'num': '1'}
    rec = {
        'security_id': f'{exchange}:{code}',
        'source_code': source,
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'request_url': URL,
        'request_params': params,
    }
    try:
        resp = session.get(URL, params=params, timeout=(8, 20))
        rec.update(http_status=resp.status_code, size_bytes=len(resp.content),
                   response_sha256=hashlib.sha256(resp.content).hexdigest())
        if resp.status_code != 200:
            rec['status'] = 'HTTP_FAILURE'
            return rec, None
        value = resp.json()
        result = value.get('result') or {}
        rec['provider_status'] = result.get('status')
        data = result.get('data') or {}
        periods = list((data.get('report_list') or {}).keys())
        rec['report_periods_returned'] = periods
        if not periods:
            rec['status'] = 'EMPTY_PERIOD_LIST'
            return rec, None
        period = periods[0]
        block = data['report_list'][period]
        items = block.get('data') or []
        rec.update(
            period_key=period,
            publish_date=block.get('publish_date'),
            report_currency=block.get('rCurrency'),
            is_audit=block.get('is_audit'),
            audit_opinion=block.get('audit_opinion'),
            is_exist_yoy=block.get('is_exist_yoy'),
            item_count=len(items),
            status='JSON_OBTAINED',
        )
        (RAW / f"{exchange}_{code}_{source}.json").write_bytes(resp.content)
        return rec, items
    except requests.RequestException as exc:
        rec.update(status='TRANSPORT_FAILURE', error_class=type(exc).__name__)
        return rec, None


def main():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})
    records, inventory = [], {}
    for exchange, code, name in SAMPLES:
        for source, cn in STATEMENTS:
            rec, items = probe(session, exchange, code, source)
            rec['stock_name'] = name
            rec['statement_cn'] = cn
            records.append(rec)
            if not items:
                continue
            for idx, item in enumerate(items):
                key = (source, item.get('item_field'), item.get('item_title'))
                row = inventory.setdefault(key, {
                    'statement': source,
                    'item_field': item.get('item_field'),
                    'item_title': item.get('item_title'),
                    'display_type': item.get('item_display_type'),
                    'display': item.get('item_display'),
                    'precision': item.get('item_precision'),
                    'seen_in': [],
                    'null_seen': 0,
                    'empty_string_seen': 0,
                    'numeric_seen': 0,
                    'first_index': idx,
                })
                row['seen_in'].append(f'{exchange}:{code}')
                raw = item.get('item_value')
                if raw is None:
                    row['null_seen'] += 1
                elif str(raw).strip() == '':
                    row['empty_string_seen'] += 1
                else:
                    row['numeric_seen'] += 1
                    row.setdefault('example_value', raw)
                    row.setdefault('example_security', f'{exchange}:{code}')
    inv_rows = sorted(inventory.values(), key=lambda r: (r['statement'], r['first_index']))
    for r in inv_rows:
        r['seen_in'] = '|'.join(r['seen_in'])
        r['sample_count'] = len(r['seen_in'].split('|'))
    (OUT / 'provider_probe_records.json').write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (OUT / 'provider_field_inventory.csv').open('w', encoding='utf-8', newline='') as f:
        cols = ['statement', 'item_field', 'item_title', 'display_type', 'display', 'precision',
                'first_index', 'sample_count', 'seen_in', 'numeric_seen', 'null_seen',
                'empty_string_seen', 'example_security', 'example_value']
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in inv_rows:
            w.writerow({k: r.get(k, '') for k in cols})
    ok = sum(1 for r in records if r['status'] == 'JSON_OBTAINED')
    print(json.dumps({'probes': len(records), 'json_ok': ok, 'inventory_rows': len(inv_rows),
                      'out': str(OUT)}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
