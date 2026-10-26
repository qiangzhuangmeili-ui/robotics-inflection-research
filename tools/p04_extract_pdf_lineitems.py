"""P04 证据采集 B：官方年报 PDF 中合并三表与"分季度主要财务数据"的行项目、页码、单位与样例数值。

只读本机已回读的 Drive 缓存 PDF（sources/ 仓库忽略），不下载、不改原件。
输出 runs/issues/P04/pdf_lineitem_evidence.json：
每个目标行项目属于哪个 document_id、哪一物理页、原文标签、同行前两个数值，
用于 provider_field_mapping 的"官方原文证据"列与单位核对。
"""
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
CACHE = ROOT / 'sources/drive_readback_20261026'

SAMPLES = [
    {'document_id': 'DOC-055EAAF729BDBA32', 'file': 'DOC-055EAAF729BDBA32.pdf', 'stock_code': '688218',
     'stock_name': '江苏北人', 'exchange': 'SH', 'period': 'FY2025'},
    {'document_id': 'DOC-2025AR-002354', 'file': 'DOC-2025AR-002354.pdf', 'stock_code': '002354',
     'stock_name': '天娱数科', 'exchange': 'SZ', 'period': 'FY2025'},
    {'document_id': 'DOC-2025AR-920207', 'file': 'DOC-2025AR-920207.pdf', 'stock_code': '920207',
     'stock_name': '众诚科技', 'exchange': 'BJ', 'period': 'FY2025'},
    {'document_id': 'DOC-2026H1-920207', 'file': 'DOC-2026H1-920207.pdf', 'stock_code': '920207',
     'stock_name': '众诚科技', 'exchange': 'BJ', 'period': '2026H1'},
]

HEADINGS = ['合并资产负债表', '母公司资产负债表', '合并利润表', '母公司利润表',
            '合并现金流量表', '母公司现金流量表']
PREFIX = re.compile(r'^(?:[0-9一二三四五六七八九十]+[、\.．]|[（(][一二三四五六七八九十0-9]+[)）]|其中[：:]|加[：:]|减[：:])+')

TARGETS = {
    'BS': ['货币资金', '应收账款', '应收票据', '合同资产', '存货', '资产总计'],
    'IS': ['营业总收入', '营业收入', '营业成本', '营业总成本', '营业利润', '利润总额',
           '净利润', '归属于母公司所有者的净利润', '基本每股收益'],
    'CF': ['销售商品、提供劳务收到的现金', '经营活动产生的现金流量净额'],
}
SPECIAL_TABLES = {
    'KEY_FINANCIALS': '主要会计数据',
    'NONRECURRING': '非经常性损益项目',
    'QUARTERLY': '分季度',
}
MONEY = re.compile(r'-?\d{1,3}(?:,\d{3})+\.\d{2}|-?\d+\.\d{2}')


def normalize(line):
    line = line.replace(' ', '').replace('\u3000', '')
    line = PREFIX.sub('', line)
    return line


def page_texts(path):
    reader = PdfReader(str(path))
    return [(p.extract_text() or '') for p in reader.pages]


def heading_positions(texts):
    found = []
    for idx, text in enumerate(texts):
        for raw in text.split('\n'):
            line = raw.strip().replace(' ', '')
            if not line or len(line) > 20:
                continue
            norm = PREFIX.sub('', line)
            if norm in HEADINGS:
                found.append((idx, norm))
                break
    return found


def statement_ranges(texts):
    positions = heading_positions(texts)
    ranges = {}
    for i, (idx, head) in enumerate(positions):
        if head.startswith('合并') and head not in ranges:
            nxt = positions[i + 1][0] if i + 1 < len(positions) else len(texts) - 1
            ranges[head] = (idx, max(nxt - 1, idx))
    return ranges, positions


def numbers_after(line, limit=3):
    """只取金额形态（含千分位或两位小数），避免把附注编号'七(1)'误当数值。"""
    nums = MONEY.findall(line)
    return nums[:limit] if nums else []


def find_item(texts, start, end, label):
    variants = [label, label.replace('归属于母公司所有者的', '归属于母公司股东的')]
    for idx in range(start, end + 1):
        lines = [l.strip() for l in texts[idx].split('\n')]
        for pos, line in enumerate(lines):
            if not line:
                continue
            norm = normalize(line)
            if any(norm.startswith(v) for v in variants):
                nums = numbers_after(line)
                if not nums:  # 数值折到下一行
                    tail = ' '.join(lines[pos + 1:pos + 3])
                    nums = numbers_after(tail)
                    line = (line + ' ⟶ ' + tail).strip()
                return idx, line, nums
    # 折行兜底：整页去掉空白后匹配
    for idx in range(start, end + 1):
        flat = re.sub(r'\s', '', texts[idx])
        for v in variants:
            pos = flat.find(v)
            if pos >= 0:
                seg = flat[pos:pos + 140]
                return idx, flat[max(0, pos - 10):pos + 100], numbers_after(seg)
    return None, None, []


def table_page(texts, needle):
    for idx, text in enumerate(texts):
        if needle in text:
            return idx
    return None


def main():
    evidence, structure = [], []
    for sample in SAMPLES:
        path = CACHE / sample['file']
        base = {k: sample[k] for k in ('document_id', 'stock_code', 'stock_name', 'exchange', 'period')}
        if not path.exists():
            structure.append({**base, 'status': 'LOCAL_CACHE_MISSING'})
            continue
        texts = page_texts(path)
        ranges, positions = statement_ranges(texts)
        structure.append({
            **base, 'pages': len(texts), 'status': 'TEXT_EXTRACTED',
            'headings': [{'page': p + 1, 'heading': h} for p, h in positions],
            'ranges': {k: [v[0] + 1, v[1] + 1] for k, v in ranges.items()},
        })
        for head, key in [('合并资产负债表', 'BS'), ('合并利润表', 'IS'), ('合并现金流量表', 'CF')]:
            if head not in ranges:
                evidence.append({**base, 'statement': key, 'statement_heading': head,
                                 'target': None, 'status': 'STATEMENT_RANGE_NOT_FOUND'})
                continue
            start, end = ranges[head]
            unit = cur = None
            for idx in range(start, min(start + 2, len(texts))):
                m = re.search(r'单位[：:]\s*(元|千元|万元|百万元)', texts[idx])
                c = re.search(r'币种[：:]\s*([^\s，,]+)', texts[idx])
                unit = unit or (m.group(1) if m else None)
                cur = cur or (c.group(1) if c else None)
            for label in TARGETS[key]:
                page, line, nums = find_item(texts, start, end, label)
                evidence.append({
                    **base, 'statement': key, 'statement_heading': head,
                    'statement_pages': f'{start + 1}-{end + 1}', 'target': label,
                    'page': page + 1 if page is not None else None,
                    'raw_line': (line or '')[:200], 'values_found': nums,
                    'unit_on_statement': unit, 'currency_on_statement': cur,
                    'status': 'FOUND' if page is not None else 'LABEL_NOT_FOUND_IN_RANGE',
                })
        for key, needle in SPECIAL_TABLES.items():
            page = table_page(texts, needle)
            block = heading = ''
            if page is not None:
                lines = [l.strip() for l in texts[page].split('\n') if l.strip()]
                hit = next((i for i, l in enumerate(lines) if needle in l), 0)
                heading = lines[hit]
                block = ' | '.join(lines[hit:hit + 22])
            evidence.append({
                **base, 'statement': key, 'statement_heading': heading or needle, 'target': needle,
                'page': page + 1 if page is not None else None, 'raw_line': block[:900],
                'values_found': numbers_after(block, 6), 'unit_on_statement': None,
                'currency_on_statement': None,
                'status': 'FOUND' if page is not None else 'TABLE_NOT_FOUND',
            })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'pdf_lineitem_evidence.json').write_text(
        json.dumps({'samples': SAMPLES, 'document_structure': structure, 'line_items': evidence},
                   ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    found = sum(1 for e in evidence if e['status'] == 'FOUND')
    print(json.dumps({'samples': len(SAMPLES), 'evidence_rows': len(evidence), 'found': found,
                      'ranges': {s['document_id']: s.get('ranges') for s in structure}}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
