"""把 002415 / 002611 的 2026 半年报从英文版换成中文原版。

文档身份（security_id|主体类型|报告类型|期间|revision）不变，所以 document_id 不变；
换的是「同一身份下的错误语种副本」。旧文件留档，台账逐字段更新并记录 sha 变化。
"""
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
INDEX = ROOT / 'runs/collection/collection_index.csv'
CST = timezone(timedelta(hours=8))

TARGETS = [
    dict(code='002415', sec='SZ:002415', slot='h1_2026', doc='DOC-BD004DAB21E5E1CE',
         cn=HERE / 'download_cn/002415_2026H1_CN.pdf',
         title='2026年半年度报告', published='2026-07-25', pages=139,
         url='https://static.cninfo.com.cn/finalpage/2026-07-25/1225440236.PDF'),
    dict(code='002611', sec='SZ:002611', slot='h1_2026', doc='DOC-A9E7E15C4BAEE74E',
         cn=HERE / 'download_cn/002611_2026H1_CN.pdf',
         title='2026年半年度报告', published='2026-07-28', pages=177,
         url='https://static.cninfo.com.cn/finalpage/2026-07-28/1225443200.PDF'),
]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    rows = list(csv.DictReader(open(INDEX, encoding='utf-8-sig')))
    header = list(rows[0].keys())
    backup = HERE / 'superseded_english'
    backup.mkdir(exist_ok=True)
    log = []
    now = datetime.now(CST).isoformat(timespec='seconds')

    for t in TARGETS:
        rec = next(r for r in rows if r['security_id'] == t['sec'] and r['slot_id'] == t['slot'])
        assert rec['document_id'] == t['doc'], (rec['document_id'], t['doc'])
        old_path = ROOT / rec['local_file']
        old_sha = sha(old_path)
        old_title, old_url, old_bytes = rec['title'], rec['primary_url'], rec['bytes']
        shutil.copy2(old_path, backup / f"{t['doc']}_EN.pdf")

        new_bytes = t['cn'].read_bytes()
        new_sha = hashlib.sha256(new_bytes).hexdigest()
        assert new_bytes[:4] == b'%PDF'
        new_rel = f"sources/collection/originals/{t['code']}/{t['slot']}/{t['doc']}.pdf"
        dest = ROOT / new_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new_bytes)

        rec.update(title=t['title'], published_on=t['published'], primary_url=t['url'],
                   page_count=str(t['pages']), bytes=str(len(new_bytes)), sha256=new_sha,
                   local_file=new_rel, updated_at=now,
                   status_reason='原采集为英文版（非中文原版），2026-10-30 换为巨潮中文原版；'
                                 '文档身份不变，旧英文件留档 m07_repair_20261030/superseded_english')
        log.append(dict(security_id=t['sec'], stock_code=t['code'], slot=t['slot'],
                        document_id=t['doc'], old_title=old_title, old_url=old_url,
                        old_sha256=old_sha, old_bytes=old_bytes,
                        new_title=t['title'], new_url=t['url'], new_sha256=new_sha,
                        new_bytes=len(new_bytes), replaced_at=now))

    with open(INDEX, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    (HERE / 'doc_replacement.json').write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                               encoding='utf-8')
    print(json.dumps(log, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
