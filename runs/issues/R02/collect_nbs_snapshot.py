#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R02 / #46 一次性采集：国家统计局官方行业信号快照（联网，仅执行一次）。

用途
----
从 https://www.stats.gov.cn/sj/zxfb/ 及其翻页抓取披露日 <= 2026-10-25 的官方原文，
解析工业增加值/主要工业产品产量、PPI、制造业 PMI，固化为
runs/issues/R02/nbs_official_sources_snapshot.json。

纪律
----
1. 本脚本需要联网，**不属于**离线复现链路；step_r02_build.py / step_r02_verify.py
   只读取已固化的 JSON，绝不再联网。
2. 只采用披露日 <= 2026-10-25 的页面；晚于截止日的页面一律丢弃。
3. 官方原文未单列的指标一律记 UNKNOWN，绝不编造或跨口径拼接。
4. 抓取前清空 HTTP_PROXY/HTTPS_PROXY（见 _opener）。
5. 单月口径与累计口径使用**不同 metric_key**（_M / _CUM），杜绝跨期混算。
6. 输出纯 LF、UTF-8，时间戳由 R02_FIXED_NOW 固定（默认 2026-11-26T15:00:00+08:00）。

运行
----
    R02_FIXED_NOW=2026-11-26T15:00:00+08:00 py runs/issues/R02/collect_nbs_snapshot.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lxml import html as LH

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs/issues/R02/nbs_official_sources_snapshot.json"

CUTOFF = "2026-10-25"
TZ = timezone(timedelta(hours=8))
NOW = os.environ.get("R02_FIXED_NOW") or "2026-11-26T15:00:00+08:00"

BASE = "https://www.stats.gov.cn/sj/zxfb/"
LISTING_PAGES = [BASE + "index.html"] + [BASE + ("index_%d.html" % i) for i in range(1, 15)]

# source_id: (相对路径, 单月期别, 累计期别)
TARGETS = {
    "IVA_202609": ("202610/t20261019_1965617.html", "202609", "2026Q1Q3"),
    "IVA_202606": ("202607/t20260715_1964123.html", "202606", "2026H1"),
    "IVA_202512": ("202601/t20260119_1962329.html", "202512", "2025FY"),
    "PPI_202609": ("202610/t20261014_1965476.html", "202609", "2026Q1Q3"),
    "PPI_202606": ("202607/t20260709_1964083.html", "202606", "2026H1"),
    "PPI_202512": ("202601/t20260109_1962272.html", "202512", "2025FY"),
    "PMI_202609": ("202609/t20260930_1965449.html", "202609", None),
    "PMI_202606": ("202606/t20260630_1964032.html", "202606", None),
    "PMI_202512": ("202512/t20251231_1962218.html", "202512", None),
}

PREV_MONTH = {"202512": "202511", "202606": "202605", "202609": "202608"}

BASE_PERIOD = {
    "2025FY": "2024FY",
    "2026H1": "2025H1",
    "2026Q1Q3": "2025Q1Q3",
    "202512": "202412",
    "202606": "202506",
    "202609": "202509",
}

IVA_INDUSTRY_ROWS = [
    ("IVA_TOTAL", "规模以上工业增加值", "规模以上工业增加值"),
    ("IVA_MANUFACTURING", "制造业增加值", "制造业"),
    ("IVA_GENERAL_EQUIPMENT", "通用设备制造业增加值", "通用设备制造业"),
    ("IVA_SPECIAL_EQUIPMENT", "专用设备制造业增加值", "专用设备制造业"),
    ("IVA_AUTOMOTIVE", "汽车制造业增加值", "汽车制造业"),
    ("IVA_ELECTRICAL_MACHINERY", "电气机械和器材制造业增加值", "电气机械和器材制造业"),
    ("IVA_COMPUTER_ELECTRONICS", "计算机、通信和其他电子设备制造业增加值", "计算机、通信和其他电子设备制造业"),
]

IVA_PRODUCT_ROWS = [
    ("ROBOT_INDUSTRIAL_OUTPUT", "工业机器人产量", "工业机器人（套）"),
    ("ROBOT_SERVICE_OUTPUT", "服务机器人产量", "服务机器人（套）"),
]

PMI_ROWS = [
    ("PMI_MANUFACTURING", "制造业采购经理指数", r"制造业采购经理指数（PMI）为([\d.]+)%"),
    ("PMI_PRODUCTION", "制造业生产指数", r"生产指数为([\d.]+)%"),
    ("PMI_NEW_ORDERS", "制造业新订单指数", r"新订单指数为([\d.]+)%"),
    ("PMI_NON_MANUFACTURING", "非制造业商务活动指数", r"非制造业商务活动指数为([\d.]+)%"),
    ("PMI_COMPOSITE", "综合PMI产出指数", r"综合PMI产出指数为([\d.]+)%"),
]

BOUNDARY = {
    "IVA": "规模以上工业增加值增速为扣除价格因素的实际增速，覆盖年主营业务收入2000万元及以上工业企业，不等于本池企业营收增速，也不等于机器人业务收入增速。",
    "PRODUCT": "产量为规模以上工业企业口径的实物产量，含出口与库存变动，不等于本池企业机器人业务收入或订单。",
    "PPI": "PPI为工业生产者出厂价格指数，反映工业品出厂价格总水平，不等于本池企业实际产品售价或毛利率。",
    "PPI_CUM": "累计平均同比为年初至当期的平均涨幅，与单月同比不可相互替代。",
    "PMI": "PMI为采购经理月度问卷调查的扩散指数（50为荣枯线），反映环比方向而非同比幅度，不代表本池企业订单或收入。",
}

SCOPE = {
    "IVA": "规模以上工业企业（年主营业务收入2000万元及以上）",
    "PRODUCT": "规模以上工业企业主要工业产品产量",
    "PPI": "全国工业生产者出厂价格调查",
    "PPI_CUM": "全国工业生产者出厂价格调查（累计平均）",
    "PMI": "制造业采购经理调查样本企业",
}


def _opener():
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(k, None)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


OPENER = _opener()


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (R02 evidence capture)"})
    with OPENER.open(req, timeout=40) as r:
        return r.status, r.read()


def paragraphs(raw: bytes):
    doc = LH.fromstring(raw)
    for el in doc.xpath("//script|//style"):
        el.getparent().remove(el)
    ps = [re.sub(r"\s+", " ", p.text_content()).strip() for p in doc.xpath("//p")]
    return [p for p in ps if p]


def table_rows(raw: bytes, idx: int = 0):
    doc = LH.fromstring(raw)
    tables = doc.xpath("//table")
    if len(tables) <= idx:
        return []
    out = []
    for tr in tables[idx].xpath(".//tr"):
        cells = [re.sub(r"\s+", " ", c.text_content()).strip() for c in tr.xpath("./td|./th")]
        cells = [c for c in cells if c]
        if cells:
            out.append(cells)
    return out


def num(s):
    s = (s or "").replace(",", "").replace("−", "-").replace("—", "-").strip()
    if s in ("", "…", "-", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def disclosure_date(raw: bytes, rel: str) -> str:
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})", " ".join(paragraphs(raw)[:2]))
    if m:
        return "%s-%s-%s" % m.groups()
    m = re.search(r"t(\d{4})(\d{2})(\d{2})_", rel)
    if not m:
        raise SystemExit("cannot determine disclosure date for " + rel)
    return "%s-%s-%s" % m.groups()


def title_of(raw: bytes) -> str:
    doc = LH.fromstring(raw)
    t = doc.xpath("//title")
    return re.sub(r"\s+", " ", t[0].text_content()).strip() if t else ""


def signed(m) -> float:
    v = float(m.group(2))
    if m.group(1) == "下降":
        return -v
    if m.group(1) == "持平":
        return 0.0
    return v


def mk_metric(key, name, period, ptype, value, unit, yoy, mom, scope_kind, boundary_kind, quote, locator):
    return {
        "metric_key": key,
        "metric_name_cn": name,
        "period_key": period,
        "period_type": ptype,
        "base_period_key": BASE_PERIOD[period],
        "value": value,
        "unit": unit,
        "yoy_pct": yoy,
        "mom_change_pp": mom,
        "sample_scope": SCOPE[scope_kind],
        "interpretation_boundary": BOUNDARY[boundary_kind],
        "scope_conflict_flag": "NO",
        "quote_locator": locator,
        "exact_quote": quote,
    }


def build_iva(rel: str, m_period: str, c_period: str):
    status, raw = fetch(BASE + rel)
    if status != 200:
        raise SystemExit("HTTP %s for %s" % (status, rel))
    ps = paragraphs(raw)
    rows = table_rows(raw, 0)
    if not rows:
        raise SystemExit("no table rows for " + rel)
    caption = next((p for p in ps if "规模以上工业生产主要数据" in p), "")
    metrics = []
    for key, name, label in IVA_INDUSTRY_ROWS + IVA_PRODUCT_ROWS:
        hit = next((r for r in rows if r[0] == label), None)
        if hit is None or len(hit) < 5:
            continue
        is_product = key.startswith("ROBOT_")
        unit = "套" if is_product else "%"
        quote = " | ".join(hit)
        locator = "正文表格「%s」" % caption
        if is_product:
            metrics.append(mk_metric(key + "_M", name + "（单月）", m_period, "MONTHLY",
                                     num(hit[1]), unit, num(hit[2]), None, "PRODUCT", "PRODUCT", quote, locator))
            metrics.append(mk_metric(key + "_CUM", name + "（累计）", c_period, "CUMULATIVE",
                                     num(hit[3]), unit, num(hit[4]), None, "PRODUCT", "PRODUCT", quote, locator))
        else:
            metrics.append(mk_metric(key + "_YOY_M", name + "同比（单月）", m_period, "MONTHLY",
                                     num(hit[2]), unit, num(hit[2]), None, "IVA", "IVA", quote, locator))
            metrics.append(mk_metric(key + "_YOY_CUM", name + "同比（累计）", c_period, "CUMULATIVE",
                                     num(hit[4]), unit, num(hit[4]), None, "IVA", "IVA", quote, locator))
    lead = next((p for p in ps if "规模以上工业增加值同比实际增长" in p), "")
    return {
        "http_status": status,
        "raw_html_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_html_bytes": len(raw),
        "title": title_of(raw),
        "disclosure_date": disclosure_date(raw, rel),
        "exact_quote": lead,
        "metrics": metrics,
    }


def build_ppi(rel: str, m_period: str, c_period: str):
    status, raw = fetch(BASE + rel)
    if status != 200:
        raise SystemExit("HTTP %s for %s" % (status, rel))
    ps = paragraphs(raw)
    head = next((p for p in ps if "全国工业生产者出厂价格" in p and "同比" in p), "")
    if not head:
        raise SystemExit("no PPI headline for " + rel)
    metrics = []
    m = re.search(r"工业生产者出厂价格同比(上涨|下降|持平)([\d.]+)%", head)
    if not m:
        raise SystemExit("cannot parse PPI yoy for " + rel)
    mq = re.search(r"环比(上涨|下降|持平)([\d.]+)%", head)
    metrics.append(mk_metric("PPI_EXFACTORY_YOY_M", "工业生产者出厂价格同比（单月）", m_period, "MONTHLY",
                             signed(m), "%", signed(m), signed(mq) if mq else None, "PPI", "PPI", head, "正文首段"))
    # 「一、工业生产者价格同比变动情况」紧随其后的段落含生产资料/加工工业同比
    hdr = next((i for i, p in enumerate(ps) if "工业生产者价格同比变动情况" in p), None)
    seg = ps[hdr + 1] if hdr is not None and hdr + 1 < len(ps) else head
    m2 = re.search(r"生产资料价格(?:同比)?(上涨|下降|持平)([\d.]+)%", seg)
    if not m2:
        raise SystemExit("cannot parse PPI production goods yoy for " + rel)
    metrics.append(mk_metric("PPI_PRODUCTION_GOODS_YOY_M", "生产资料出厂价格同比（单月）", m_period, "MONTHLY",
                             signed(m2), "%", signed(m2), None, "PPI", "PPI", seg, "正文「一、工业生产者价格同比变动情况」"))
    m3 = re.search(r"加工工业价格(上涨|下降|持平)([\d.]+)%", seg)
    if not m3:
        raise SystemExit("cannot parse PPI processing yoy for " + rel)
    metrics.append(mk_metric("PPI_PROCESSING_YOY_M", "加工工业出厂价格同比（单月）", m_period, "MONTHLY",
                             signed(m3), "%", signed(m3), None, "PPI", "PPI", seg, "正文「一、工业生产者价格同比变动情况」"))
    mc = re.search(r"(?:1—\d+月平均|上半年|全年)[，,]?\s*工业生产者出厂价格(?:比上年同期)?(上涨|下降|持平)([\d.]+)%", head)
    if mc:
        metrics.append(mk_metric("PPI_CUMULATIVE_AVG_YOY_CUM", "工业生产者出厂价格累计平均同比", c_period, "CUMULATIVE",
                                 signed(mc), "%", signed(mc), None, "PPI_CUM", "PPI_CUM", head, "正文首段"))
    else:
        raise SystemExit("cannot parse PPI cumulative average for " + rel)
    return {
        "http_status": status,
        "raw_html_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_html_bytes": len(raw),
        "title": title_of(raw),
        "disclosure_date": disclosure_date(raw, rel),
        "exact_quote": head,
        "metrics": metrics,
    }


def build_pmi(rel: str, m_period: str):
    status, raw = fetch(BASE + rel)
    if status != 200:
        raise SystemExit("HTTP %s for %s" % (status, rel))
    ps = paragraphs(raw)
    metrics = []
    for key, name, pat in PMI_ROWS:
        sent = next((p for p in ps if re.search(pat, p)), "")
        m = re.search(pat, sent)
        if not m:
            continue
        mm = re.search(r"比上月(上升|下降|持平)([\d.]+)个百分点", sent)
        mom = signed(mm) if mm else (0.0 if "与上月持平" in sent else None)
        item = mk_metric(key, name, m_period, "MONTHLY", float(m.group(1)), "index",
                         None, mom, "PMI", "PMI", sent, "正文分项段落")
        # PMI 为环比扩散指数：基期取上月，而非上年同月
        item["base_period_key"] = PREV_MONTH[m_period]
        metrics.append(item)
    head = next((p for p in ps if re.search(r"制造业采购经理指数（PMI）为[\d.]+%", p)), "")
    return {
        "http_status": status,
        "raw_html_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_html_bytes": len(raw),
        "title": title_of(raw),
        "disclosure_date": disclosure_date(raw, rel),
        "exact_quote": head,
        "metrics": metrics,
    }


COVERAGE_NOTES = [
    {
        "metric_key": "ROBOT_SERVICE_OUTPUT",
        "status": "DISCLOSED_SEPARATELY",
        "note": "服务机器人在「规模以上工业主要产品产量」表中单独列示（单位：套），三期单月与累计口径均可取得，故不使用 UNKNOWN。",
    },
    {
        "metric_key": "PPI_SUBINDUSTRY_ROBOT_SPECIFIC",
        "status": "UNKNOWN",
        "note": "官方原文未单列机器人/减速器/伺服等细分产品出厂价格指数，仅公布总体、生产资料/生活资料及加工工业等大类，故记 UNKNOWN，不做推断。",
    },
    {
        "metric_key": "NBS_ROBOT_INDUSTRY_VA",
        "status": "UNKNOWN",
        "note": "国民经济行业分类中无独立「机器人制造业」大类，官方未单列机器人行业增加值，只能取通用设备/专用设备/电气机械/计算机电子等上位行业，故记 UNKNOWN。",
    },
]


def main():
    sources = []
    for sid, (rel, m_period, c_period) in TARGETS.items():
        if sid.startswith("IVA_"):
            parsed = build_iva(rel, m_period, c_period)
            kind = "IVA"
        elif sid.startswith("PPI_"):
            parsed = build_ppi(rel, m_period, c_period)
            kind = "PPI"
        else:
            parsed = build_pmi(rel, m_period)
            kind = "PMI"

        if parsed["disclosure_date"] > CUTOFF:
            raise SystemExit("page %s disclosed %s exceeds cutoff %s" % (sid, parsed["disclosure_date"], CUTOFF))
        if not parsed["metrics"]:
            raise SystemExit("no metrics parsed for " + sid)

        sources.append({
            "source_id": "NBS_" + sid,
            "source_name": "国家统计局·数据发布",
            "source_url": BASE + rel,
            "title": parsed["title"],
            "disclosure_date": parsed["disclosure_date"],
            "period_key": m_period,
            "fact_or_forecast": "FACT",
            "exact_quote": parsed["exact_quote"],
            "http_status": parsed["http_status"],
            "raw_html_bytes": parsed["raw_html_bytes"],
            "raw_html_sha256": parsed["raw_html_sha256"],
            "parsed_metrics": parsed["metrics"],
        })

    cat = {}
    for s in sources:
        for m in s["parsed_metrics"]:
            e = cat.setdefault(m["metric_key"], {
                "metric_key": m["metric_key"],
                "metric_name_cn": m["metric_name_cn"],
                "unit": m["unit"],
                "period_type": m["period_type"],
                "periods": [],
            })
            if m["period_key"] not in e["periods"]:
                e["periods"].append(m["period_key"])

    for e in cat.values():
        e["periods"].sort()

    snapshot = {
        "artifact": "R02_NBS_OFFICIAL_SOURCES_SNAPSHOT",
        "issue_key": "R02",
        "issue_number": 46,
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": CUTOFF,
        "captured_at": NOW,
        "capture_method": "ONE_TIME_HTTP_FETCH_WITH_PROXY_CLEARED",
        "publisher": "国家统计局",
        "publisher_domain": "www.stats.gov.cn",
        "listing_urls": LISTING_PAGES,
        "cutoff_rule": "仅采用 disclosure_date <= %s 的官方原文；晚于该日的页面（如 2026年10月PMI、2026年10月PPI、2026年10月工业增加值）一律排除。" % CUTOFF,
        "offline_note": "本文件为固化快照；step_r02_build.py 与 step_r02_verify.py 只读本文件，不再联网。",
        "source_count": len(sources),
        "metric_count": len(cat),
        "metric_catalog": [cat[k] for k in sorted(cat)],
        "sources": sources,
        "coverage_notes": COVERAGE_NOTES,
        "not_disclosed": [n for n in COVERAGE_NOTES if n["status"] == "UNKNOWN"],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    print("wrote", OUT.relative_to(REPO))
    print("sources", len(sources), "metrics", len(cat))
    for k in sorted(cat):
        print("  %-34s %s" % (k, cat[k]["periods"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
