"""补采 002415 / 002611 的 2026 年半年度报告中文原版（池内现为英文版）。

只下载 + 校验，不写台账；校验通过后再人工确认替换。
"""
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
OUT = Path(__file__).parent / 'download_cn'
OUT.mkdir(exist_ok=True)

TARGETS = [
    dict(code='002415', name='海康威视', sec='SZ:002415',
         url='https://static.cninfo.com.cn/finalpage/2026-07-25/1225440236.PDF',
         title='2026年半年度报告', published='2026-07-25'),
    dict(code='002611', name='东方精工', sec='SZ:002611',
         url='https://static.cninfo.com.cn/finalpage/2026-07-28/1225443200.PDF',
         title='2026年半年度报告', published='2026-07-28'),
]


def fetch(url, dest):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    dest.write_bytes(data)
    return data


def main():
    from pypdf import PdfReader
    report = []
    for t in TARGETS:
        dest = OUT / f"{t['code']}_2026H1_CN.pdf"
        data = fetch(t['url'], dest)
        head = data[:8]
        sha = hashlib.sha256(data).hexdigest()
        info = dict(**t, path=str(dest.relative_to(ROOT)) if str(dest).startswith(str(ROOT)) else str(dest),
                    bytes=len(data), sha256=sha, magic_ok=head.startswith(b'%PDF'))
        try:
            reader = PdfReader(str(dest))
            info['pages'] = len(reader.pages)
            text = '\n'.join((reader.pages[i].extract_text() or '') for i in range(min(12, len(reader.pages))))
            info['text_chars_12p'] = len(text)
            flat = re.sub(r'\s+', '', text)
            info['has_title_2026h1'] = '2026年半年度报告' in flat
            info['has_npdedt'] = '扣除非经常性损益' in flat
            zh = len(re.findall(r'[\u4e00-\u9fff]', text))
            info['zh_ratio'] = round(zh / max(len(text), 1), 3)
            info['head'] = text[:120].replace('\n', ' ')
        except Exception as exc:                      # noqa: BLE001
            info['error'] = str(exc)
        report.append(info)
        print(json.dumps(info, ensure_ascii=False, indent=1))
    (OUT / 'download_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                              encoding='utf-8')


if __name__ == '__main__':
    main()
