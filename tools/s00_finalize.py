"""S00 收口：压缩大表、补齐文件指纹、生成交付清单 manifest.json。

issue #35 约定「原件/大表存 Drive 或本机缓存，不提交 GitHub」，
故 financial_normalized.csv 本机保留明文 + 提交 .gz（5.5 MB），
manifest 同时记录两者 sha256 与行数，任何人可解压复算。
"""
import csv
import gzip
import hashlib
import io
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/S00'

DELIVERABLES = [
    ('financial_normalized.csv', '全池财务标准化长表（逐格原值/单位/倍数/页码/来源）', True),
    ('financial_normalized.csv.gz', '同上，gzip 版（提交 Git 用）', True),
    ('normalization_issues.csv', '标准化问题清单（缺失/不适用/未披露/校验失败/重算标记）', True),
    ('normalization_manifest.json', '标准化清单：口径、覆盖、校验汇总、可比性矩阵、已知限制', True),
    ('legacy_snapshot_conflicts.json', '旧快照与官方 PDF 的逐条冲突明细（V3）', True),
    ('extract/extract_run_summary.json', '12 槽抽取总汇总', True),
]


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with io.open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def count_rows(path):
    if path.suffix == '.csv':
        with io.open(path, encoding='utf-8-sig') as f:
            return max(sum(1 for _ in f) - 1, 0)
    return None


def main():
    src = OUT / 'financial_normalized.csv'
    gz = OUT / 'financial_normalized.csv.gz'
    if src.exists():
        h = hashlib.sha256()
        # mtime=0：gzip 头不写时间戳，同一份内容重复压缩得到同一 sha256，
        # 否则复核方每次重压都看到不同哈希，无法证明「gz 与明文一致」
        with io.open(src, 'rb') as f, io.open(gz, 'wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=6, mtime=0) as g:
                while True:
                    b = f.read(1 << 20)
                    if not b:
                        break
                    h.update(b)
                    g.write(b)
        print(f'[S00] gz {os.path.getsize(gz)/2**20:.1f} MB, csv sha256={h.hexdigest()[:16]}')

    # 12 槽抽取明细的指纹（不逐份提交，但记录可复算依据）
    extract_files = []
    for p in sorted((OUT / 'extract').glob('*_fields.csv')):
        extract_files.append({'file': str(p.relative_to(OUT)).replace('\\', '/'),
                              'bytes': p.stat().st_size,
                              'sha256': sha256_of(p),
                              'data_rows': count_rows(p)})

    nm_path = OUT / 'normalization_manifest.json'
    nm = json.load(io.open(nm_path, encoding='utf-8'))
    nm['outputs'] = {
        'financial_normalized.csv': {
            'rows': count_rows(src), 'bytes': src.stat().st_size, 'sha256': sha256_of(src),
            'note': '明文大表留本机，不入 Git；解压 .gz 可逐字节复现'},
        'financial_normalized.csv.gz': {
            'bytes': gz.stat().st_size, 'sha256': sha256_of(gz), 'committed': True},
        'normalization_issues.csv': {
            'rows': count_rows(OUT / 'normalization_issues.csv'),
            'bytes': (OUT / 'normalization_issues.csv').stat().st_size,
            'sha256': sha256_of(OUT / 'normalization_issues.csv')},
    }
    nm['extract_artifacts'] = extract_files
    json.dump(nm, io.open(nm_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    items = []
    for name, desc, required in DELIVERABLES:
        p = OUT / name
        rec = {'file': name, 'desc': desc, 'required_by_issue': required, 'exists': p.exists()}
        if p.exists():
            rec['bytes'] = p.stat().st_size
            rec['sha256'] = sha256_of(p)
            if name.endswith('.csv'):
                rec['data_rows'] = count_rows(p)
        items.append(rec)

    manifest = {
        'issue_key': 'S00',
        'issue_number': 35,
        'plan_version': '20261026_collection_first_v2',
        'executor': 'WorkBuddy AI',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'review_nature': 'SELF_CHECK',
        'scope': '全池财务标准化：12 个采集槽 + 旧快照 2021/2022 补充，保留原值/单位/倍数/来源/版本，'
                 '派生单季与毛利率，标记缺失/上市前/重述/低基数，检查合计关系与来源',
        'deliverables': items,
        'extract_artifacts': extract_files,
        'git_policy': '逐格抽取明细（extract/*_fields.csv，约 37 MB）与 76.7 MB 明文大表不入 Git；'
                      '提交 .gz（5.5 MB）+ 本 manifest 的 sha256，可解压复算',
    }
    json.dump(manifest, io.open(OUT / 'manifest.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(f'[S00] manifest.json written, {len(items)} deliverables')


if __name__ == '__main__':
    main()
