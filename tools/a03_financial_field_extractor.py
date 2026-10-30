"""A03 财务字段抽取器：从官方定期报告 PDF 抽取 P00 必需字段的原值、单位与页码证据。

设计原则（与 P04 字段字典一致）：
1. 只读本机已回读原件，不下载、不改原件、不写回台账状态。
2. 只取「合并」报表，绝不与母公司报表混用。
3. 区分四种结果：EXTRACTED / NOT_IN_STATEMENT（报表无该科目）/ NOT_FOUND（定位到报表但取不到值）/ STATEMENT_NOT_FOUND。
4. 单位必须从表头检测，检测不到写 UNKNOWN，不默认按「元」处理。
5. 金额保留原值字符串 + 换算倍数 + 换算后数值，便于 S00 复核。
6. 分季度表措辞有三种变体（主要财务指标 / 主要财务数据），标签跨行是常态。

用法：
    python tools/a03_financial_field_extractor.py --limit 12 --tag sample
    python tools/a03_financial_field_extractor.py --all --workers 6
"""
import argparse
import csv
import io
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/A03'
INDEX = ROOT / 'runs/collection/collection_index.csv'

# ---------------------------------------------------------------- 正则

# 金额：允许千分位；排除日期片段（前后不能紧邻数字或小数点）
MONEY = re.compile(r'(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d.])')
# 单位：兼容「单位：元币种：人民币」「单位：人民币元」「单位：千元」
UNIT_RE = re.compile(r'单位\s*(?:[:：为]\s*)?(?:人民币)?\s*(百万元|千万元|千元|万元|元)')
UNIT_SCALE = {'元': 1, '千元': 1000, '万元': 10000, '千万元': 10000000, '百万元': 1000000}
# 摘要表数字列包括金额和同比百分比；百分比可能超过 1000%，不能按数值大小过滤。
TABLE_NUMBER = re.compile(
    r'(?<![\d.])([+-]?(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?)(\s*%)?'
)
# 行首编号/前缀
PREFIX = re.compile(
    r'^(?:[一二三四五六七八九十]+[、.．]|[（(][一二三四五六七八九十\d]+[)）]'
    r'|其中\s*[:：]|加\s*[:：]|减\s*[:：]|\d+[、.．]|\(\d+\)|（\d+）)+'
)

TITLES = {
    '合并资产负债表': 'BS_CONS',
    '母公司资产负债表': 'BS_PARENT',
    '合并利润表': 'IS_CONS',
    '母公司利润表': 'IS_PARENT',
    '合并现金流量表': 'CF_CONS',
    '母公司现金流量表': 'CF_PARENT',
    '合并所有者权益变动表': 'EQ_CONS',
    '母公司所有者权益变动表': 'EQ_PARENT',
}

# 标题变体（S00 实测新增）：深市三季报写作「2、合并年初到报告期末利润表」
# 「3、合并年初到报告期末现金流量表」；也有「年初至报告期末」写法。
# 用 $ 锚定整行，避免把正文里「合并资产负债表项目」这类小标题当成报表标题。
TITLE_VARIANTS = [
    (re.compile(r'^合并(?:年初到报告期末|年初至报告期末|本报告期)?利润表$'), 'IS_CONS'),
    (re.compile(r'^母公司(?:年初到报告期末|年初至报告期末|本报告期)?利润表$'), 'IS_PARENT'),
    (re.compile(r'^合并(?:年初到报告期末|年初至报告期末|本报告期)?现金流量表$'), 'CF_CONS'),
    (re.compile(r'^母公司(?:年初到报告期末|年初至报告期末|本报告期)?现金流量表$'), 'CF_PARENT'),
    (re.compile(r'^合并资产负债表$'), 'BS_CONS'),
    (re.compile(r'^母公司资产负债表$'), 'BS_PARENT'),
]

# 分季度表字段：label 候选，按顺序尝试
QUARTERLY_FIELDS = [
    ('FIN.REV.SQ', ['营业收入']),
    ('FIN.NPP.SQ', ['归属于上市公司股东的净利润', '归属于母公司股东的净利润', '归属于母公司所有者的净利润']),
    ('FIN.NPDEDT.SQ', ['归属于上市公司股东的扣除非经常性损益后的净利润',
                       '归属于上市公司股东的扣除非经常性损益的净利润',
                       '扣除非经常性损益后的净利润', '扣除非经常性损益的净利润']),
    ('FIN.OCF.SQ', ['经营活动产生的现金流量净额']),
]

# 三表字段：(statement, 字段, label 候选, use_merge)
# 资产负债表一律 use_merge=False（空科目不得串行取值）；利润表/现金流量表 use_merge=True（长标签换行）
STATEMENT_FIELDS = [
    ('BS_CONS', 'FIN.AR.INSTANT', ['应收账款'], False),
    ('BS_CONS', 'FIN.NR.INSTANT', ['应收票据'], False),
    ('BS_CONS', 'FIN.CONTRACTASSET.INSTANT', ['合同资产'], False),
    ('BS_CONS', 'FIN.INV.INSTANT', ['存货'], False),
    ('BS_CONS', 'FIN.ASSET.INSTANT', ['资产总计'], False),
    ('IS_CONS', 'FIN.REV.YTD', ['营业收入'], True),
    ('IS_CONS', 'FIN.COST.YTD', ['营业成本'], True),
    ('IS_CONS', 'FIN.NP.YTD', ['净利润'], True),
    ('IS_CONS', 'FIN.NPP.YTD', ['归属于母公司股东的净利润', '归属于母公司所有者的净利润'], True),
    ('CF_CONS', 'FIN.OCF.YTD', ['经营活动产生的现金流量净额'], True),
]

# 这些标签若出现在候选行首，说明不是目标科目（避免误取）
EXCLUDE_SUFFIX = {
    'FIN.AR.INSTANT': ('融资', '净额', '坏账', '减值'),
    'FIN.NR.INSTANT': ('融资', '净额'),
    'FIN.CONTRACTASSET.INSTANT': ('减值',),
    'FIN.INV.INSTANT': ('跌价', '减值'),
    'FIN.REV.YTD': ('增长', '成本'),
    'FIN.COST.YTD': ('增长',),
    'FIN.NP.YTD': ('率', '增长'),
}


# ---------------------------------------------------------------- 基础工具

def normalize(line):
    # 去掉所有空白：北交所/部分沪市 PDF 会把标签拆成「归属于 挂牌公司股东的扣 除非经常性损益」
    s = re.sub(r'\s+', '', line.replace('\u3000', ''))
    return PREFIX.sub('', s).strip()


def money_values(text):
    out = []
    for m in MONEY.finditer(text):
        try:
            out.append((m.group(0), float(m.group(0).replace(',', ''))))
        except ValueError:
            pass
    return out


def amounts(text):
    """取「像金额」的值：带千分位或绝对值 >= 1000。

    利润表里附注编号会写成「5.31」「7.12」，格式与金额相同；若直接取第一个数字，
    「其中：营业收入 5.31 180,045,879.67」会被抽成 5.31。附注编号不可能带千分位，
    也不可能上千，所以用这两条把编号排掉。整行确实只有小金额时（如 0.00）回退到全部。
    """
    vals = money_values(text)
    big = [v for v in vals if ',' in v[0] or abs(v[1]) >= 1000]
    return big if big else vals


def page_lines(text):
    return [x.strip() for x in (text or '').split('\n') if x.strip()]


def is_title(line):
    # 深市写「1、合并资产负债表」、北交所写「（一） 合并资产负债表 」，须先剥编号前缀
    s = normalize(line).replace(' ', '').lstrip('、.．')
    # 部分公司把合并与母公司并列在同一张表中；仅匹配明确的合并标题，
    # 不把没有合并标识的单体报表默认为合并。实际取第一列并要求合并列在前。
    s = re.sub(r'^\d{4}年(?:半年度|年度|第一季度|第三季度)?', '', s)
    s = s.replace('合并及公司', '合并').replace('合并及母公司', '合并')
    s = re.sub(r'(利润表|现金流量表)[（(](?:年初至本季度|年初至报告期末|年初到报告期末)[）)]$', r'\1', s)
    key = TITLES.get(s)
    if key:
        return key
    for pat, k in TITLE_VARIANTS:
        if pat.match(s):
            return k
    return None


def detect_unit(lines):
    for ln in lines:
        m = UNIT_RE.search(ln.replace(' ', ''))
        if m:
            return m.group(1)
        # 审计报表常直接写“2026年6月30日 人民币元”，没有“单位”二字。
        if len(ln) < 65:
            m = re.search(r'人民币\s*(百万元|千万元|千元|万元|元)(?:\s|[)）]|$)', ln)
            if m:
                return m.group(1)
    return None


def table_values(text):
    """取摘要表一行里的全部数值列，保留带 % 的列以维持表格列位置。"""
    out = []
    for m in TABLE_NUMBER.finditer(text):
        raw = m.group(1)
        try:
            out.append((raw, float(raw.replace(',', '')), bool(m.group(2))))
        except ValueError:
            continue
    return out


def summary_cells(text):
    """保留摘要表空位与百分比列；禁止按金额大小压缩列位置。"""
    # “净利润（净亏损以‘-’号填列）”中的减号是说明文字，不是空数据列。
    text = re.sub(r'[（(][^()（）]*[亏损失][^()（）]*[)）]', '', text)
    tokens = re.compile(TABLE_NUMBER.pattern + r'|不适用|[—－–]+|(?<![\d.])--?(?![\d.])')
    out = []
    for m in tokens.finditer(text):
        if m.group(1) is None:
            out.append((m.group(0), None, False))
        else:
            out.append((m.group(1), float(m.group(1).replace(',', '')), bool(m.group(2))))
    return out


def join_ahead(lines, i, max_ahead=3):
    """从第 i 行起最多拼接 max_ahead 行，直到出现金额。返回 (文本, 用了多少行) 或 (None, 0)。"""
    acc = lines[i]
    if MONEY.search(acc):
        return acc, 1
    for k in range(1, max_ahead + 1):
        if i + k >= len(lines):
            break
        acc = acc + lines[i + k]
        if MONEY.search(acc):
            return acc, k + 1
    return None, 0


# ---------------------------------------------------------------- 单份 PDF 解析

def parse_pdf(path, max_scan=300):
    """返回 dict：pages(文本列表)、n_pages、error。"""
    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
    except Exception as exc:                      # noqa: BLE001
        return {'pages': [], 'n_pages': 0, 'error': f'OPEN_FAILED: {exc}'}
    pages = []
    limit = min(n, max_scan)
    for i in range(limit):
        try:
            pages.append(reader.pages[i].extract_text() or '')
        except Exception as exc:                  # noqa: BLE001
            pages.append('')
            if i == 0:
                return {'pages': pages, 'n_pages': n, 'error': f'PAGE_TEXT_FAILED: {exc}'}
    return {'pages': pages, 'n_pages': n, 'error': None}


def find_quarterly_table(pages, scan=60):
    """定位分季度表所在页与行。

    返回 (page_no, lines, unit, reason)。reason='NO_QUARTERLY_SECTION' 表示全篇没有分季度章节
    （北交所部分挂牌公司格式如此），这是「无此表」而非「解析失败」。
    """
    for pi in range(min(scan, len(pages))):
        lines = page_lines(pages[pi])
        head = None
        for idx, ln in enumerate(lines):
            if '分季度' in ln and ('财务指标' in ln or '财务数据' in ln):
                head = idx
                break
        if head is None:
            continue
        body = []
        for ln in lines[head + 1:]:
            if '非经常性损益' in ln and '项目' in ln:
                break
            if '季度数据与' in ln:
                break
            body.append(ln)
        if not body:
            return pi + 1, [], detect_unit(lines), 'QUARTERLY_TITLE_NO_BODY'
        unit = detect_unit(body) or detect_unit(lines)
        return pi + 1, body, unit, None
    # 扩大确认：全篇是否真的没有「分季度」字样
    for pi in range(len(pages)):
        if '分季度' in (pages[pi] or ''):
            return None, [], None, 'QUARTERLY_BEYOND_SCAN_RANGE'
    return None, [], None, 'NO_QUARTERLY_SECTION'


def merge_rows(lines, max_ahead=4):
    """把跨行的标签行合并成逻辑行：不含金额的行向后拼接，直到出现金额。

    分季度表里「归属于上市公司股东 / 的扣除非经常性损益 / 的净利润 / 44,139,266.91 ...」
    这种三行标签是常态，不合并就无法匹配。
    """
    out = []
    i = 0
    while i < len(lines):
        acc = lines[i]
        j = i
        while (not MONEY.search(acc)) and j + 1 < len(lines) and (j - i) < max_ahead:
            j += 1
            acc = acc + lines[j]
        out.append((acc, i))
        i = j + 1
    return out


def is_quarter_header(line):
    """季度表头行（含「季度」且无金额），须在合并前剔除，否则会被拼进第一行数据。"""
    return ('季度' in line) and (not MONEY.search(line))


def extract_quarterly(pages):
    """返回 {field_id: (value_str, page, label)} 与未命中原因。"""
    page_no, body, unit, reason = find_quarterly_table(pages)
    if page_no is None:
        return {}, unit, reason
    body = [ln for ln in body if not is_quarter_header(ln)]
    rows = merge_rows(body)
    got = {}
    for field_id, labels in QUARTERLY_FIELDS:
        for label in labels:
            hit = None
            for text, _i in rows:
                norm = normalize(text)
                pos = norm.find(label)
                if pos < 0 or pos > 40:
                    continue
                rest = norm[pos + len(label):]
                if rest.startswith(('增长', '率', '变动', '比例')):
                    continue
                vals = amounts(text)
                if len(vals) >= 4:
                    hit = (vals[:4], label, text)
                    break
            if hit:
                got[field_id] = (hit[0], page_no, hit[1], hit[2])
                break
    return got, unit, None


def extract_q3_single_quarter(pages):
    """三季报「主要会计数据」表的「本报告期」列（Q3 单季）。

    与 extract_quarterly 的区别：三季报没有「分季度财务指标」章节，单季数在
    「主要会计数据」表的第 1 列（本报告期），累计数在第 3 列。百分比会被 amounts 过滤，
    所以 2 个金额 = (单季, 累计)，1 个金额 = 只有累计（单季列为「--」）。
    """
    for pi in range(min(6, len(pages))):
        text = pages[pi] or ''
        if '本报告期' not in text or '年初至报告期末' not in text:
            continue
        lines = page_lines(text)
        rows = merge_rows(lines)
        got = {}
        for field_id, labels in QUARTERLY_FIELDS:
            for label in labels:
                hit = None
                for row_text, _i in rows:
                    norm = normalize(row_text)
                    pos = norm.find(label)
                    if pos < 0 or pos > 40:
                        continue
                    rest = norm[pos + len(label):]
                    if rest.startswith(('增长', '率', '变动', '比例')):
                        continue
                    vals = amounts(row_text)
                    if len(vals) >= 2:
                        hit = (vals[0][0], pi + 1, label, row_text)
                        break
                if hit:
                    got[field_id] = hit
                    break
        if got:
            return got, detect_unit(lines), None
    return {}, None, 'NO_Q3_CURRENT_PERIOD_TABLE'


REPORT_FEATURES = {
    'BS_CONS': ('货币资金', '资产总计', '流动资产合计', '负债合计'),
    'BS_PARENT': ('货币资金', '资产总计', '流动资产合计', '负债合计'),
    'IS_CONS': ('营业收入', '营业成本', '净利润'),
    'IS_PARENT': ('营业收入', '营业成本', '净利润'),
    'CF_CONS': ('经营活动产生的现金流量净额', '销售商品', '收到的现金', '购建固定资产'),
    'CF_PARENT': ('经营活动产生的现金流量净额', '销售商品', '收到的现金', '购建固定资产'),
}


def _looks_like_statement(pages, pi, key, span=2):
    """报表标题还要过一道「这一页真像报表吗」的检验。

    S00 实测北交所一季报：第 3 页有独占行「合并资产负债表」、第 4 页有「合并现金流量表」，
    但它们属于「主要财务数据变动情况」章节的小标题（下一行才是「项目 期末余额 期初余额 变动比例」），
    真正的三表在第 9-17 页。只按标题文字匹配会把变动说明页当成报表区块，
    导致 BS 区域错位、OCF 整段漏抽（920002/920060 各期复现）。
    判据：该页及其后 span 页里，必须命中该报表的 2 个以上科目特征词。
    """
    feats = REPORT_FEATURES.get(key)
    if not feats:
        return True
    text = ''
    for k in range(pi, min(pi + span + 1, len(pages))):
        text += (pages[k] or '')
    flat = re.sub(r'\s+', '', text)
    return sum(1 for f in feats if f in flat) >= 2


def build_statement_map(pages, start_page=None):
    """扫描报表标题，返回 {statement_key: (start_idx, end_idx, unit)}。

    标题在正文里是独占行（带「1、」「（一）」等编号前缀），附注里的引用是长句不会被 is_title 命中；
    但目录页也可能是独占行，所以要求 BS_CONS 之后 15 页内出现 BS_PARENT 或 IS_CONS 才认作正文区块。

    start_page 默认自适应：年报（>40 页）前 15 页是封面/目录/摘要，跳过；
    季报（10-20 页）第 5-6 页就是合并资产负债表，固定 15 会整份漏抽（S00 实测深市/沪市季报均如此）。
    """
    if start_page is None:
        start_page = 2 if len(pages) < 40 else 15
    hits = []
    for pi in range(min(start_page, len(pages)), len(pages)):
        for ln in page_lines(pages[pi]):
            key = is_title(ln)
            if key and re.search(r'合并及(?:母公司|公司)', normalize(ln)):
                flat = re.sub(r'\s+', '', pages[pi])
                if not any(header in flat for header in ('合并合并公司公司', '合并合并母公司母公司')):
                    # 并列表必须在表头验证合并两列在前；列序不明保持未知。
                    continue
            if key and _looks_like_statement(pages, pi, key):
                hits.append((pi, key))

    start_idx = None
    for idx, (pi, key) in enumerate(hits):
        if key != 'BS_CONS':
            continue
        window = [h[1] for h in hits[idx + 1:] if h[0] <= pi + 15]
        if 'BS_PARENT' in window or 'IS_CONS' in window:
            start_idx = idx
            break
    if start_idx is None:
        return {}

    regions = {}
    current = None
    for pi, key in hits[start_idx:]:
        if current and current[0] == key:
            continue
        if current:
            regions.setdefault(current[0], [current[1], pi])
        current = (key, pi)
        if key in ('EQ_CONS', 'EQ_PARENT'):
            break
    if current:
        regions.setdefault(current[0], [current[1], len(pages) - 1])

    out = {}
    for key, (s, e) in regions.items():
        unit = None
        for pi in range(s, min(e + 1, s + 4)):
            unit = detect_unit(page_lines(pages[pi]))
            if unit:
                break
        out[key] = (s, e, unit)
    return out


STATEMENT_MONEY = re.compile(r'(?<![\d.])\(?-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2}|\d+)\)?(?![\d.])')


def statement_amounts(text, note_column=False):
    """三表专用：兼容整数和括号负数，排除附注序号与百分比。

    不扩宽摘要表和季度表的正则，以免把年份/注号当金额。
    中文附注号先剥离；无格式的小整数附注只在后续有两列金额时剥离。
    """
    note_pattern = r'(?:注\s*\d+(?=\s|$|[：:])|[一二三四五六七八九十]+\s*[、(（]\s*\d+(?:[.、]\d+)*[)）]?)'
    explicit_note = bool(re.search(note_pattern, text))
    text = re.sub(note_pattern, '', text)
    text = re.sub(r'\(\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*\)', lambda m:'-'+m.group(1).lstrip('+-'), text)
    out = []
    for m in STATEMENT_MONEY.finditer(text):
        if text[m.end():].lstrip().startswith('%'):
            continue
        raw = m.group(0)
        if raw.startswith('(') and raw.endswith(')'):
            raw = '-' + raw[1:-1].lstrip('+-')
        out.append((raw, float(raw.replace(',', ''))))
    if not explicit_note and note_column and len(summary_cells(text)) >= 3 and out and re.fullmatch(r'\d{1,3}', out[0][0]):
        out = out[1:]
    # 附注可能是 5.31 / 7.12；保留原实现的过滤规则。
    elif not explicit_note and note_column and len(summary_cells(text)) >= 3 and out and re.fullmatch(r'\d{1,2}\.\d{2}', out[0][0]):
        out = out[1:]
    return out


def extract_statement_field(pages, regions, statement, field_id, labels, use_merge):
    """在指定报表区域内按行首标签取第一个金额。

    匹配方式为「从第 i 行起向后滑动拼接 1~3 行」，而不是把整页先合并成逻辑行：
    后者会把无关的短行（如「归属于少数股东的其他综合收益的」）吞进标签前面，导致标签不在行首。
    use_merge=True 用于利润表/现金流量表（长标签换行是常态）；
    use_merge=False 用于资产负债表——科目为空时标签独占一行，合并会把下一科目金额错记过来
    （A02 已指出合同资产「未列示」不得填 0），必须严格单行并区分 BLANK_IN_STATEMENT。
    """
    if statement not in regions:
        return None, None, None, 'STATEMENT_NOT_FOUND'
    s, e, _unit = regions[statement]
    note_column = any('附注' in ln for p in pages[s:min(e + 1, s + 2)] for ln in page_lines(p)[:18])
    excl = EXCLUDE_SUFFIX.get(field_id, ())
    # PDF逐单元格输出时资产负债表也可能是“标签/本期/上期”三行。
    # 以下科目边界检查禁止吞下一科目，只接受数值或附注续行。
    spans = (1, 2, 3, 4, 5)
    blank_found = False
    for pi in range(s, min(e + 1, len(pages))):
        lines = page_lines(pages[pi])
        n = len(lines)
        for i in range(n):
            for span in spans:
                if i + span > n:
                    break
                text = ' '.join(lines[i:i + span])
                norm = normalize(text)
                for label in labels:
                    if not norm.startswith(label):
                        continue
                    rest = norm[len(label):]
                    if any(rest.lstrip().startswith(x) for x in excl):
                        continue
                    # 空白科目不得吞掉下一科目；只有没有新中文标签的数值续行可拼接。
                    if span > 1:
                        prior = normalize(''.join(lines[i:i + span - 1]))
                        tail = normalize(lines[i + span - 1])
                        if prior.startswith(label) and re.match(r'^[\u4e00-\u9fff]', tail) and not tail.startswith('注'):
                            return None, pi + 1, label, 'BLANK_IN_STATEMENT'
                    # 当前列为破折号时保留空值，不能改取上年或右半张表的数。
                    current_text = re.sub(r'注\s*\d+(?=\s|$|[：:])', '', text)
                    current_text = re.sub(r'[一二三四五六七八九十]+\s*[、(（]\s*\d+(?:[.、]\d+)*[)）]?', '', current_text)
                    current_cells = summary_cells(current_text)
                    had_explicit_note = bool(re.search(r'注\s*\d+|[一二三四五六七八九十]+\s*[、(（]\s*\d+', text))
                    if note_column and not had_explicit_note and len(current_cells) >= 3 and re.fullmatch(r'\d{1,3}(?:\.\d{2})?', current_cells[0][0]):
                        current_cells = current_cells[1:]
                    if current_cells and current_cells[0][1] is None:
                        return None, pi + 1, label, 'BLANK_IN_STATEMENT'
                    vals = statement_amounts(text, note_column=note_column)
                    if vals:
                        return vals[0][0], pi + 1, label, None
                    if span == 1:
                        blank_found = True
    return None, None, None, ('BLANK_IN_STATEMENT' if blank_found else 'NOT_IN_STATEMENT')


def _checkbox_value(seg):
    """从「□是 √否」这类勾选片段判定取值。

    PDF 文本提取常把 √/☑ 丢掉，只剩「□是 否」。此时不能因为「□是」就判「是」——
    方框表示**未**勾选。正确判据是：哪个选项前面没有方框，哪个就是被勾选的。
    两个都带方框或都不带，则无法判断，返回 None 交人工，不猜。
    """
    m = re.search(r'[√☑✓✔]\s*(是|否)', seg)
    if m:
        return m.group(1)
    has_box_yes = bool(re.search(r'[□☐]\s*是', seg))
    has_box_no = bool(re.search(r'[□☐]\s*否', seg))
    if has_box_yes and not has_box_no:
        return '否'
    if has_box_no and not has_box_yes:
        return '是'
    return None


def extract_restatement(pages, scan=60):
    """重述/追溯调整标记。

    深市/北交所在「主要会计数据」前有勾选项「公司是否需追溯调整或重述以前年度会计数据」；
    沪市格式没有该勾选项，须回附注「会计政策变更 / 前期差错更正」章节判断。
    返回 (flag, page, evidence, method)。
    """
    # 1) 勾选项
    for pi in range(min(scan, len(pages))):
        lines = page_lines(pages[pi])
        for i, ln in enumerate(lines):
            flat = ln.replace(' ', '')
            if '追溯调整' in flat and '重述' in flat:
                seg = ' '.join(lines[i:i + 3])
                val = _checkbox_value(seg)
                if val:
                    return val, pi + 1, seg[:160], 'CHECKBOX'
                # 深市部分公司不画方框，直接把结果单独写成一行「是」/「否」
                if not re.search(r'[□☐√☑✓✔]', seg):
                    for w in lines[i + 1:i + 4]:
                        w2 = w.strip().replace(' ', '')
                        if w2 in ('是', '否'):
                            return w2, pi + 1, seg[:160], 'CHECKBOX_LINE'
                if '不适用' in seg:
                    return 'NOT_APPLICABLE', pi + 1, seg[:160], 'CHECKBOX'

    # 1.5) 摘要表同时列示「调整后」「调整前」= 明确发生追溯调整/重述，比关键词判据更硬
    for pi in range(min(scan, len(pages))):
        text = (pages[pi] or '').replace(' ', '')
        if '调整前' in text and '调整后' in text and (
                '主要会计数据' in text or '会计数据和财务指标' in text):
            return '是', pi + 1, '摘要表同时列示调整后/调整前两列', 'KEY_TABLE_ADJUSTED_COLUMNS'

    # 2) 附注关键词（沪市等无勾选项格式）
    #    只认明确否定式判「否」；肯定式只标「疑似需复核」，不直接判「是」——
    #    误判「是」会让 S00 禁止跨期相减，代价高于留 UNKNOWN。
    neg = ('无前期差错更正', '不存在前期差错更正', '本期无前期差错更正', '未发生前期差错更正',
           '无重大前期差错更正', '无会计差错更正', '无重大会计差错更正', '无追溯重述',
           '不存在追溯重述', '无会计政策变更', '未发生会计政策变更', '无重要会计政策变更')
    pos = ('前期差错更正', '追溯重述', '追溯调整以前年度', '会计差错更正')
    # 附注章节标题本身就写作「会计政策变更、会计估计变更和前期差错更正」，会稳定制造假阳性
    title_ctx = ('变更和', '变更、', '变更及', '估计变更', '政策变更', '差错更正和', '差错更正及')
    for pi in range(min(scan + 120, len(pages))):
        text = (pages[pi] or '').replace(' ', '')
        if '会计政策' not in text and '差错' not in text and '追溯' not in text:
            continue
        for k in neg:
            if k in text:
                return '否', pi + 1, k, 'NOTE_KEYWORD_NEG'
        for k in pos:
            start = 0
            while True:
                idx = text.find(k, start)
                if idx < 0:
                    break
                before = text[max(0, idx - 8):idx]
                if not any(before.endswith(x) for x in title_ctx):
                    return 'RESTATEMENT_INDICATED_NEEDS_REVIEW', pi + 1, k, 'NOTE_KEYWORD_POS'
                start = idx + len(k)
    return 'NOT_FOUND', None, None, 'NONE'


def _ytd_column_index(lines, i, span=1):
    """摘要表里「累计值」是第几个金额列（0-based）。默认 0。

    页级判定：把该页切成「被金额行分隔的连续无金额行块」，取第一个同时出现
    「本报告期」与「年初至报告期末」的块，比较两者先后。
    深市三季报「本报告期 | 增减 | 年初至报告期末 | 增减」→ 累计在第 2 列；
    北交所「项目 | 年初至报告期末(1-9月) | 上年同期 | 增减」→ 累计在第 1 列。
    """
    blocks, cur = [], []
    for ln in lines:
        if MONEY.search(ln):
            if cur:
                blocks.append(''.join(cur))
                cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(''.join(cur))
    for t in blocks:
        pos_cur = t.find('本报告期')
        pos_ytd = -1
        for key in ('年初至报告期末', '年初至本报告期末', '年初至报告期期末'):
            pos_ytd = t.find(key)
            if pos_ytd >= 0:
                break
        if pos_ytd < 0:
            continue
        if pos_cur < 0:
            return 0
        # 数值列包含同比百分比（或其空位），累计在本期/同比后的第三列。
        return 2 if pos_cur < pos_ytd else 0
    return 0


def _anchor_index(lines, anchor_value):
    """用三表已抽到的营业收入累计值反查它在摘要表行里的列下标。

    沪市三季报摘要表列宽不固定：600008 的「营业收入」行有 6 个金额
    （本报告期 | 上年同期调整前 | 上年同期调整后 | 增减% | 年初至报告期末 | 上年同期…），
    累计值在第 4 列，靠表头词序只能猜到第 1/2 列，必然取成单季。
    用三表 REV（口径唯一）当锚点定位列，再拿同一列取扣非，比任何表头启发式都硬。
    """
    if not anchor_value:
        return None
    try:
        target = float(str(anchor_value).replace(',', ''))
    except (TypeError, ValueError):
        return None
    for ln in lines:
        norm = normalize(ln)
        if not norm.startswith('营业收入'):
            continue
        if norm[len('营业收入'):].startswith(('增长', '率', '比例')):
            continue
        # 包含所有百分比列。筛掉小百分比会让列号错位；只按金额大小过滤
        # 也会漏掉 1,000% 以上的同比变化，并把它当成扣非金额。
        for k, (_raw, num, _is_percent) in enumerate(summary_cells(ln)):
            if num is not None and not _is_percent and abs(num - target) <= max(1.0, abs(target) * 1e-6):
                return k
        return None
    return None


def extract_key_financials(pages, scan=60, anchor_rev=None, with_details=False):
    """从年报摘要表取累计值，作为三表抽取的独立交叉校验源，并补三表没有的扣非累计。

    该表有三种版式：
      - 深市「六、主要会计数据和财务指标」+「本年比上年增减」
      - 沪市「七、近三年主要会计数据和财务指标」+「本期比上年同期增减(%)」
      - 北交所「第三节 会计数据和财务指标」下的「一、盈利能力」「二、营运情况」分表
    统一用「营业收入 + 归属于 + 增减」三个特征定位，比只认「主要会计数据」覆盖更全。
    """
    out = {}
    first_page = None
    unit_all = None
    carried_unit = None
    details = {}
    for pi in range(min(scan, len(pages))):
        raw_lines = page_lines(pages[pi])
        # 先在物理行边界去掉“注3”，再拼标签，避免变成 31,144,165,735。
        lines = [re.sub(r'注\s*\d+(?=\s|$|[：:])', '', line).strip() for line in raw_lines]
        text = '\n'.join(lines)
        if '营业收入' not in text or '归属于' not in text or '增减' not in text:
            carried_unit = detect_unit(lines) or carried_unit
            continue
        # 三季报摘要表多一列「年初至报告期末」，但列序两种版式完全相反：
        #   深市「本报告期 | 本报告期增减 | 年初至报告期末 | 年初至报告期末增减」→ 累计在第 2 列
        #   北交所「项目 | 年初至报告期末(1-9月) | 上年同期 | 增减比例」→ 累计在第 1 列
        #   沪市还夹「调整前/调整后」，累计可能在第 4 列
        # 优先用三表 REV 累计值当锚点反查列；拿不到锚点再退回表头词序。
        col_idx = _anchor_index(lines, anchor_rev)
        if col_idx is None:
            col_idx = _ytd_column_index(lines, 0)
        n = len(lines)
        targets = {
            'FIN.REV.YTD': ['营业收入'],
            'FIN.NPP.YTD': ['归属于上市公司股东的净利润', '归属于母公司股东的净利润',
                            '归属于挂牌公司股东的净利润'],
            'FIN.NPDEDT.YTD': ['归属于上市公司股东的扣除非经常性损益的净利润',
                               '归属于上市公司股东的扣除非经常性损益后的净利润',
                               '归属于挂牌公司股东的扣除非经常性损益后的净利润',
                               '归属于挂牌公司股东的扣除非经常性损益的净利润',
                               '归属于母公司股东的扣除非经常性损益的净利润',
                               '扣除非经常性损益后归属于上市公司股东的净利润',
                               '扣除非经常性损益后归属于公司普通股股东的净利润',
                               '扣除非经常性损益后归属于母公司股东的净利润'],
            'FIN.OCF.YTD': ['经营活动产生的现金流量净额'],
        }
        for fid, labels in targets.items():
            if fid in out:
                continue
            for i in range(n):
                for span in (1, 2, 3, 4, 5):
                    if i + span > n:
                        break
                    t = ' '.join(lines[i:i + span])
                    norm = normalize(t)
                    for label in labels:
                        if not norm.startswith(label):
                            continue
                        rest = norm[len(label):]
                        if rest.startswith(('增长', '率', '比例')):
                            continue
                        vals = summary_cells(t)
                        if vals:
                            # 三季报摘要表有两列以上金额，必须按列语义取累计值：
                            # 深市第一列是 Q3 单季、第二列才是 1-9 月累计（000026：41,360,520.65
                            # 是单季扣非，累计应为 119,737,782.83）；北交所第一列就是累计。
                            # 按营收锚点列号在所有表格数值列中取值；不可按量级过滤同比百分比，
                            # 因为高增长率可能超过 1000%。无锚点时使用表头解析的累计列。
                            # OCF 行用「— —」占位时金额列变少，越界则回退第 1 列。
                            if len(vals) <= col_idx:
                                continue
                            pick = vals[col_idx]
                            if pick[1] is None or pick[2]:
                                continue
                            out[fid] = pick[0]
                            # 单位取行项目本身或它之前最近的表头；下一子表的单位
                            # 不能回灌，跨页表头沿用前页明确单位。
                            inline = re.search(r'[（(](百万元|千万元|千元|万元|元)[）)]', t)
                            row_unit = inline.group(1) if inline else None
                            if row_unit is None:
                                row_unit = next((u for u in (detect_unit([ln]) for ln in reversed(raw_lines[:i])) if u), carried_unit)
                            details[fid] = dict(page=pi + 1, unit=row_unit, raw_row=t[:600], column_index=col_idx)
                            break
                    if fid in out:
                        break
                if fid in out:
                    break
        if out and first_page is None:
            first_page = pi
            unit = detect_unit(lines)
            if not unit:
                # 深市摘要表不写「单位：元」表头，而是把单位写进行项目：「营业收入（元）」
                joined = ''.join(lines)
                for cand in ('万元', '千元', '元'):
                    if f'（{cand}）' in joined or f'({cand})' in joined:
                        unit = cand
                        break
            unit_all = details.get('FIN.NPDEDT.YTD', {}).get('unit') or unit
        # 扣非常被排到摘要表下一页，第一页命中就返回会把它丢掉；凑齐 4 个再停
        if len(out) >= 4:
            break
        carried_unit = next((u for u in (detect_unit([ln]) for ln in reversed(raw_lines)) if u), carried_unit)
    if out:
        result = (out, (first_page + 1) if first_page is not None else None, unit_all)
    else:
        result = ({}, None, None)
    return (*result, details) if with_details else result


NPDEDT_LABELS = ['归属于上市公司股东的扣除非经常性损益的净利润',
                 '归属于上市公司股东的扣除非经常性损益后的净利润',
                 '归属于挂牌公司股东的扣除非经常性损益后的净利润',
                 '归属于挂牌公司股东的扣除非经常性损益的净利润',
                 '归属于母公司股东的扣除非经常性损益的净利润',
                 '扣除非经常性损益后归属于上市公司股东的净利润',
                 '扣除非经常性损益后归属于公司普通股股东的净利润',
                 '扣除非经常性损益后归属于母公司股东的净利润']


def find_npdedt_row(pages, scan=60, anchor_rev=None):
    """补漏通道：只找「归属于…扣除非经常性损益的净利润」一行，不碰其他字段。

    与 extract_key_financials 的差别只在三处定位缺陷，全部是「原逻辑看不见」的情形：
      1. 表头判定用去空白文本——PDF 常把「增减」劈成「增\\n减」（688001「上年同期增/减变动幅度」、
         603767「同期增减变动幅/度」），按原文本判会把整页摘要表漏掉；
      2. 摘要表跨页——沪市把扣非整行甩到次页（600143/600487），深市把「归属于」行留到次页
         （603767/603400），续页无表头，沿用表头页定下的累计列；
      3. 分页把扣非标签劈成两半（600936/600939/603239/603266/688290），把次页的标签尾接回本页。
    另外合并 pypdf 拆开的负号（002579「-」/「89,849,644.18」）。

    只在原逻辑取不到扣非时才调用，返回单行；调用方据此只补 FIN.NPDEDT.YTD，
    已入池的营收/归母/现金流一律不动。
    """
    table_col = None
    table_page = None
    table_unit = None
    for pi in range(min(scan, len(pages))):
        raw_lines = page_lines(pages[pi])
        lines = [re.sub(r'注\s*\d+(?=\s|$|[：:])', '', line).strip() for line in raw_lines]
        merged = []
        for ln in lines:
            if merged and merged[-1] in ('-', '－', '—'):
                merged[-1] = merged[-1] + ln
            else:
                merged.append(ln)
        lines = merged
        if pi + 1 < len(pages) and lines:
            nxt = [re.sub(r'注\s*\d+(?=\s|$|[：:])', '', line).strip()
                   for line in page_lines(pages[pi + 1])][:6]
            frag = []
            for ln in nxt:
                if not ln:
                    continue
                if MONEY.search(ln):
                    break
                if re.match(r'^\d+\s*/\s*\d+$', ln) or '股份有限公司' in ln \
                        or re.search(r'(年度|季度|半年度)报告\s*$', ln):
                    continue
                frag.append(ln)
                if len(''.join(frag)) >= 12:
                    break
            if frag:
                for k in (1, 2, 3):
                    if len(lines) < k:
                        continue
                    tail = ''.join(lines[-k:])
                    mm = MONEY.search(tail)
                    label_part = tail[:mm.start()].strip() if mm else tail.strip()
                    num_part = tail[mm.start():].strip() if mm else ''
                    if not label_part or len(label_part) > 40:
                        continue
                    cand = normalize(label_part + ''.join(frag))
                    if any(cand.startswith(lb) for lb in NPDEDT_LABELS):
                        lines = lines[:-k] + [label_part + ''.join(frag)
                                              + ((' ' + num_part) if num_part else '')]
                        break
        flat = re.sub(r'\s+', '', '\n'.join(lines))
        is_head = ('营业收入' in flat and '增减' in flat
                   and ('归属于' in flat or '本报告期' in flat))
        is_cont = (not is_head and table_col is not None and table_page is not None
                   and pi - table_page <= 3 and '扣除非经常性损益' in flat)
        if not (is_head or is_cont):
            continue
        if is_head:
            col = _anchor_index(lines, anchor_rev)
            if col is None:
                col = _ytd_column_index(lines, 0)
            table_col, table_page = col, pi
            table_unit = detect_unit(lines)
        else:
            col = table_col
        n = len(lines)
        for i in range(n):
            for span in (1, 2, 3, 4, 5):
                if i + span > n:
                    break
                t = ' '.join(lines[i:i + span])
                norm = normalize(t)
                for label in NPDEDT_LABELS:
                    if not norm.startswith(label):
                        continue
                    rest = norm[len(label):]
                    if rest.startswith(('增长', '率', '比例')):
                        continue
                    vals = summary_cells(t)
                    if not vals:
                        continue
                    # 续页上「变动原因」表也有扣非行，但只有一列比例；真摘要行至少两列金额
                    if is_cont and sum(1 for v in vals
                                       if v[1] is not None and not v[2]) < 2:
                        continue
                    if len(vals) <= col:
                        continue
                    pick = vals[col]
                    if pick[1] is None or pick[2]:
                        continue
                    inline = re.search(r'[（(](百万元|千万元|千元|万元|元)[）)]', t)
                    row_unit = inline.group(1) if inline else None
                    if row_unit is None:
                        row_unit = next((u for u in (detect_unit([ln]) for ln in reversed(raw_lines[:i]))
                                         if u), None)
                    # 续页没有单位行，回落到表头页的单位（H1 报告常见，否则整行只能记 UNKNOWN）
                    if row_unit is None:
                        row_unit = table_unit
                    return dict(value=pick[0], page=pi + 1, unit=row_unit,
                                raw_row=t[:600], column_index=col)
    return None


def extract_one(task):
    """单份 PDF 全字段抽取。task = dict(document_id, security_id, stock_code, slot_id, period_label, path)"""
    t0 = time.time()
    res = dict(task)
    res['n_pages'] = 0
    res['parse_error'] = None
    res['fields'] = []
    res['unit_bs'] = None
    res['unit_is'] = None
    res['unit_cf'] = None
    res['unit_q'] = None
    res['quarterly_page'] = None
    res['restatement'] = 'NOT_FOUND'
    res['restatement_page'] = None
    res['restatement_evidence'] = None
    res['elapsed_s'] = 0

    parsed = parse_pdf(task['path'])
    pages = parsed['pages']
    res['n_pages'] = parsed['n_pages']
    if parsed['error']:
        res['parse_error'] = parsed['error']
        res['elapsed_s'] = round(time.time() - t0, 2)
        return res

    text_chars = sum(len(p) for p in pages)
    res['text_chars'] = text_chars
    if text_chars < 500:
        res['parse_error'] = 'IMAGE_ONLY_NO_TEXT_LAYER'
        res['elapsed_s'] = round(time.time() - t0, 2)
        return res

    fields = []

    def push(field_id, value, unit, page, label, status, note=None, raw=None):
        scale = UNIT_SCALE.get(unit) if unit else None
        val_cny = None
        if value is not None and scale is not None:
            try:
                val_cny = round(float(value.replace(',', '')) * scale, 2)
            except ValueError:
                val_cny = None
        fields.append({
            'document_id': task['document_id'],
            'security_id': task['security_id'],
            'stock_code': task['stock_code'],
            'slot_id': task['slot_id'],
            'period_label': task['period_label'],
            'field_id': field_id,
            'value_raw': value if value is not None else '',
            'unit_raw': unit or 'UNKNOWN',
            'unit_scale': scale if scale is not None else '',
            'value_cny': val_cny if val_cny is not None else '',
            'page': page or '',
            'evidence_label': label or '',
            'extract_status': status,
            'note': note or '',
            'raw_row': (raw or '')[:200],
        })

    # 分季度
    q_got, q_unit, q_reason = extract_quarterly(pages)
    res['unit_q'] = q_unit
    res['quarterly_page'] = None
    q_status_default = {
        None: 'NOT_IN_STATEMENT',
        'NO_QUARTERLY_SECTION': 'NOT_IN_STATEMENT',
        'QUARTERLY_TITLE_NO_BODY': 'QUARTERLY_PARSE_FAILED',
        'QUARTERLY_BEYOND_SCAN_RANGE': 'QUARTERLY_PARSE_FAILED',
    }.get(q_reason, 'QUARTERLY_PARSE_FAILED')
    for fid, labels in QUARTERLY_FIELDS:
        if fid in q_got:
            vals, page, label, raw = q_got[fid]
            res['quarterly_page'] = page
            for qname, (raw_val, _num) in zip(['Q1', 'Q2', 'Q3', 'Q4'], vals):
                push(fid, raw_val, q_unit, page, label, 'EXTRACTED', note=qname, raw=raw)
        else:
            push(fid, None, q_unit, res['quarterly_page'], None, q_status_default,
                 note=q_reason or '')

    # 三表
    regions = build_statement_map(pages)
    res['unit_bs'] = regions.get('BS_CONS', (None, None, None))[2]
    res['unit_is'] = regions.get('IS_CONS', (None, None, None))[2]
    res['unit_cf'] = regions.get('CF_CONS', (None, None, None))[2]
    res['regions'] = {k: {'start_page': v[0] + 1, 'end_page': v[1] + 1, 'unit': v[2]}
                      for k, v in regions.items() if k.endswith('_CONS')}

    for statement, fid, labels, allow_join in STATEMENT_FIELDS:
        val, page, label, reason = extract_statement_field(
            pages, regions, statement, fid, labels, allow_join)
        unit = {'BS_CONS': res['unit_bs'], 'IS_CONS': res['unit_is'],
                'CF_CONS': res['unit_cf']}[statement]
        if val is None:
            push(fid, None, unit, None, None, reason or 'NOT_FOUND')
        else:
            push(fid, val, unit, page, label, 'EXTRACTED')
            if fid == 'FIN.COST.YTD' and val.startswith('-') and page:
                # P04 字段契约规定成本为正数。仅对原表明确用括号列示的
                # 成本应用展示符号转换，保留带符号原值供核验。
                if re.search(r'营业成本[^\n]*\(\s*\d', pages[page - 1]):
                    fields[-1]['value_cny'] = abs(fields[-1]['value_cny']) if fields[-1]['value_cny'] != '' else ''
                    fields[-1]['note'] = 'EXPENSE_PARENTHESIS_TO_POSITIVE_P04;raw_sign_preserved'

    # 重述
    flag, rpage, rev, rmethod = extract_restatement(pages)
    res['restatement'] = flag
    res['restatement_page'] = rpage
    res['restatement_evidence'] = rev
    res['restatement_method'] = rmethod
    push('FIN.RESTATEMENT', flag if flag in ('是', '否') else None,
         'NOT_APPLICABLE', rpage, None,
         'EXTRACTED' if flag in ('是', '否') else flag,
         note=f'method={rmethod};evidence={rev or ""}')

    # 主要会计数据表：既提供扣非累计（三表没有该科目），也用作三表抽取的交叉校验
    # 锚点 = 三表已抽到的营业收入累计值，用于在列宽不定的摘要表里定位累计列
    anchor_rev = None
    for row in fields:
        if row['field_id'] == 'FIN.REV.YTD' and row['extract_status'] == 'EXTRACTED':
            anchor_rev = row['value_raw']
            break
    kf, kf_page, kf_unit, kf_details = extract_key_financials(pages, anchor_rev=anchor_rev, with_details=True)
    if 'FIN.NPDEDT.YTD' not in kf:
        # 补漏通道：原逻辑没取到扣非时，再用跨页/换行容错扫描找一次。
        # 只补扣非这一行，营收/归母/现金流的已入池值和交叉校验结论都不动。
        nd = find_npdedt_row(pages, anchor_rev=anchor_rev)
        if nd:
            kf['FIN.NPDEDT.YTD'] = nd['value']
            kf_details['FIN.NPDEDT.YTD'] = nd
            if kf_page is None:
                kf_page = nd['page']
            if not kf_unit:
                kf_unit = nd['unit']
    res['key_financials_values'] = kf
    res['key_financials_details'] = kf_details
    res['key_financials_page'] = kf_page
    res['key_financials_unit'] = kf_unit
    if 'FIN.NPDEDT.YTD' in kf:
        kd = kf_details.get('FIN.NPDEDT.YTD', {})
        push('FIN.NPDEDT.YTD', kf['FIN.NPDEDT.YTD'], kd.get('unit') or kf_unit, kd.get('page') or kf_page,
             '归属于上市公司股东的扣除非经常性损益的净利润', 'EXTRACTED',
             note='source=主要会计数据表', raw=kd.get('raw_row'))
    else:
        push('FIN.NPDEDT.YTD', None, kf_unit, kf_page, None, 'NOT_IN_STATEMENT',
             note='source=主要会计数据表')

    # 交叉校验：三表 vs 主要会计数据表
    xcheck = {}
    extracted_ytd = {}
    for row in fields:
        if row['extract_status'] == 'EXTRACTED' and row['field_id'] in (
                'FIN.REV.YTD', 'FIN.NPP.YTD', 'FIN.OCF.YTD'):
            extracted_ytd[row['field_id']] = row['value_raw']
    for fid in ('FIN.REV.YTD', 'FIN.NPP.YTD', 'FIN.OCF.YTD'):
        if fid not in kf:
            xcheck[fid] = 'ABSENT_IN_KEY_TABLE'
        elif fid not in extracted_ytd:
            xcheck[fid] = 'MISSING_IN_STATEMENT'
        else:
            try:
                a = float(kf[fid].replace(',', ''))
                b = float(extracted_ytd[fid].replace(',', ''))
                tol = max(1.0, abs(a) * 1e-6)
                xcheck[fid] = 'MATCH' if abs(a - b) <= tol else 'MISMATCH'
            except ValueError:
                xcheck[fid] = 'UNPARSED'
    res['crosscheck_raw_legacy'] = dict(xcheck)
    # 表头单位可能不同。只在各自单位明确后按人民币元交叉校验。
    direct_rows = {r['field_id']: r for r in fields if r['extract_status'] == 'EXTRACTED'}
    for fid in ('FIN.REV.YTD', 'FIN.NPP.YTD', 'FIN.OCF.YTD'):
        if fid not in kf or fid not in direct_rows:
            continue
        unit_key = kf_details.get(fid, {}).get('unit') or kf_unit
        scale_key = UNIT_SCALE.get(unit_key)
        b = direct_rows[fid]['value_cny']
        if scale_key is None or b == '':
            xcheck[fid] = 'UNPARSED'
            continue
        a = float(kf[fid].replace(',', '')) * scale_key
        xcheck[fid] = 'MATCH' if abs(a - b) <= max(1.0, abs(a) * 1e-6) else 'MISMATCH'
    res['crosscheck'] = xcheck

    res['fields'] = fields
    res['elapsed_s'] = round(time.time() - t0, 2)
    return res


# ---------------------------------------------------------------- 批量

def load_tasks(slot_ids=None, limit=None, only_verified=True):
    rows = list(csv.DictReader(io.open(INDEX, encoding='utf-8-sig')))
    tasks = []
    for r in rows:
        if only_verified and r['status'] != 'COLLECTED_IDENTITY_VERIFIED':
            continue
        if slot_ids and r['slot_id'] not in slot_ids:
            continue
        p = ROOT / r['local_file']
        if not p.exists():
            continue
        tasks.append({
            'document_id': r['document_id'],
            'security_id': r['security_id'],
            'stock_code': r['security_id'].split(':')[1],
            'slot_id': r['slot_id'],
            'period_label': r['period_label'],
            'path': str(p),
        })
    tasks.sort(key=lambda x: (x['slot_id'], x['security_id']))
    if limit:
        # 跨市场均匀取样，避免只抽到一个交易所
        by_mkt = {}
        for t in tasks:
            by_mkt.setdefault(t['security_id'].split(':')[0], []).append(t)
        picked = []
        while len(picked) < limit and any(by_mkt.values()):
            for m in ['SZ', 'SH', 'BJ']:
                if by_mkt.get(m) and len(picked) < limit:
                    picked.append(by_mkt[m].pop(0))
        tasks = picked
    return tasks


FIELDS_HEADER = ['document_id', 'security_id', 'stock_code', 'slot_id', 'period_label',
                 'field_id', 'value_raw', 'unit_raw', 'unit_scale', 'value_cny',
                 'page', 'evidence_label', 'extract_status', 'note', 'raw_row']

DIAG_HEADER = ['document_id', 'security_id', 'stock_code', 'slot_id', 'period_label',
               'n_pages', 'text_chars', 'parse_error', 'quarterly_page', 'restatement',
               'restatement_method', 'unit_bs', 'unit_is', 'unit_cf', 'unit_q',
               'key_financials_page', 'key_financials_unit', 'elapsed_s',
               'bs_start', 'bs_end', 'is_start', 'is_end', 'cf_start', 'cf_end',
               'xcheck_rev', 'xcheck_npp', 'xcheck_ocf', 'xcheck_pass']


def xcheck_verdict(xc):
    """把逐字段交叉校验结果压成一个文档级结论。"""
    if not xc:
        return 'NO_KEY_TABLE'
    vals = list(xc.values())
    if all(v == 'ABSENT_IN_KEY_TABLE' for v in vals):
        return 'NO_KEY_TABLE'
    if any(v.startswith('MISMATCH') for v in vals):
        return 'MISMATCH'
    if any(v in ('MISSING_IN_STATEMENT', 'UNPARSED') for v in vals):
        return 'PARTIAL'
    return 'MATCH'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slots', default='annual_2025',
                    help='逗号分隔的 slot_id，默认 annual_2025')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--tag', default='run')
    args = ap.parse_args()

    slot_ids = [s.strip() for s in args.slots.split(',') if s.strip()]
    limit = None if args.all else (args.limit or 12)
    tasks = load_tasks(slot_ids, limit)
    print(f'[A03] tasks={len(tasks)} slots={slot_ids} workers={args.workers}', flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    t0 = time.time()
    if args.workers <= 1:
        for i, t in enumerate(tasks, 1):
            results.append(extract_one(t))
            if i % 25 == 0:
                print(f'  {i}/{len(tasks)} {time.time()-t0:.0f}s', flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(extract_one, t): t for t in tasks}
            done = 0
            for fu in as_completed(futs):
                try:
                    results.append(fu.result())
                except Exception as exc:          # noqa: BLE001
                    t = futs[fu]
                    results.append({**t, 'fields': [], 'parse_error': f'WORKER_FAILED: {exc}',
                                    'n_pages': 0, 'text_chars': 0, 'elapsed_s': 0})
                done += 1
                if done % 50 == 0:
                    print(f'  {done}/{len(tasks)} {time.time()-t0:.0f}s', flush=True)

    results.sort(key=lambda x: (x['slot_id'], x['security_id']))
    suffix = f'_{args.tag}' if args.tag else ''
    fpath = OUT / f'financial_fields_extracted{suffix}.csv'
    dpath = OUT / f'extraction_diagnostics{suffix}.csv'
    jpath = OUT / f'extraction_summary{suffix}.json'

    n_fields = 0
    with io.open(fpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS_HEADER)
        w.writeheader()
        for r in results:
            for row in r.get('fields', []):
                w.writerow(row)
                n_fields += 1

    with io.open(dpath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=DIAG_HEADER)
        w.writeheader()
        for r in results:
            reg = r.get('regions', {})
            xc = r.get('crosscheck', {})
            xpass = xcheck_verdict(xc)
            w.writerow({
                'document_id': r['document_id'], 'security_id': r['security_id'],
                'stock_code': r['stock_code'], 'slot_id': r['slot_id'],
                'period_label': r['period_label'], 'n_pages': r.get('n_pages', 0),
                'text_chars': r.get('text_chars', 0), 'parse_error': r.get('parse_error') or '',
                'quarterly_page': r.get('quarterly_page') or '',
                'restatement': r.get('restatement') or '',
                'restatement_method': r.get('restatement_method') or '',
                'unit_bs': r.get('unit_bs') or '', 'unit_is': r.get('unit_is') or '',
                'unit_cf': r.get('unit_cf') or '', 'unit_q': r.get('unit_q') or '',
                'key_financials_page': r.get('key_financials_page') or '',
                'key_financials_unit': r.get('key_financials_unit') or '',
                'elapsed_s': r.get('elapsed_s', 0),
                'bs_start': reg.get('BS_CONS', {}).get('start_page', ''),
                'bs_end': reg.get('BS_CONS', {}).get('end_page', ''),
                'is_start': reg.get('IS_CONS', {}).get('start_page', ''),
                'is_end': reg.get('IS_CONS', {}).get('end_page', ''),
                'cf_start': reg.get('CF_CONS', {}).get('start_page', ''),
                'cf_end': reg.get('CF_CONS', {}).get('end_page', ''),
                'xcheck_rev': xc.get('FIN.REV.YTD', ''),
                'xcheck_npp': xc.get('FIN.NPP.YTD', ''),
                'xcheck_ocf': xc.get('FIN.OCF.YTD', ''),
                'xcheck_pass': xpass,
            })

    # 汇总
    from collections import Counter
    st = Counter()
    per_field = {}
    for r in results:
        for row in r.get('fields', []):
            st[row['extract_status']] += 1
            per_field.setdefault(row['field_id'], Counter())[row['extract_status']] += 1
    errs = Counter(r.get('parse_error') for r in results if r.get('parse_error'))
    xstat = Counter()
    for r in results:
        xstat[xcheck_verdict(r.get('crosscheck', {}))] += 1
    summary = {
        'tag': args.tag,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'slots': slot_ids,
        'documents': len(results),
        'field_rows': n_fields,
        'status_counts': dict(st),
        'crosscheck_docs': dict(xstat),
        'per_field': {k: dict(v) for k, v in per_field.items()},
        'parse_errors': {str(k): v for k, v in errs.items()},
        'elapsed_s': round(time.time() - t0, 1),
        'avg_s_per_doc': round(sum(r.get('elapsed_s', 0) for r in results) / max(len(results), 1), 2),
    }
    json.dump(summary, io.open(jpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:2500], flush=True)
    print(f'[A03] wrote {fpath.name} {dpath.name} {jpath.name}', flush=True)


if __name__ == '__main__':
    main()
