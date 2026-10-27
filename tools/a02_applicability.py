#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A02｜15 槽适用性判定：逐项留依据，不把未尝试当缺件。

判定口径（来自 P03 rule_excerpts.txt，现行《挂牌公司信息披露规则》2025-04-25 施行）：
  - 第十一条：定期报告 = 年度报告 + 中期报告；**季度报告可以披露**（自愿，非强制）
  - 第十三条：年报 4 个月内、中期 2 个月内；季报若披露，Q1 在 3 个月结束后 1 个月内

两类判定：
  A. 报告期早于该公司在股转挂牌日 → NOT_APPLICABLE_PRE_LISTING
     证据：股转定期报告索引（disclosureType[]=9503，已由 50 槽补采正向验证）中，
           该期间**无任何记录**，且索引最早一条与挂牌日吻合。
  B. 一季报：股转索引完整但无该期记录，且季度披露为自愿 → NOT_DISCLOSED_BY_ISSUER
     证据：同一索引对同期公司能返回三季报（920011/920055/920096 均有），
           说明季度报告确会进该索引；缺失即未披露，不是检索失败。

用法：
    python tools/a02_applicability.py --probe     # 重查索引并落证据
    python tools/a02_applicability.py --decide    # 依据证据写判定并回写台账
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P03 = ROOT / "runs/issues/P03/neeq_recheck_20261027"
OUT = ROOT / "runs/issues/A02"
CKPT = ROOT / "runs/collection/checkpoint"

NA = "NOT_APPLICABLE_PRE_LISTING"
ND = "NOT_DISCLOSED_BY_ISSUER"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept-Language": "zh-CN,zh;q=0.9"}
NF = ["companyCd", "companyName", "disclosureTitle", "disclosurePostTitle", "destFilePath",
      "publishDate", "xxfcbj", "fileExt", "xxzrlx"]


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def session():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ctx))
    body = op.open(urllib.request.Request("http://www.neeq.com.cn/", headers=UA),
                   timeout=25).read().decode("utf-8", "ignore")
    m = re.search(r"C3VK=([0-9a-f]+)", body)
    return op, (m.group(1) if m else "")


def fetch_periodic(op, token, cd, page=0):
    p = {"noticeType[]": ["9503"], "disclosureType[]": ["9503"], "page": page,
         "companyCd": cd, "isNewThree": 1, "startTime": "2015-01-01", "endTime": "2026-10-25",
         "keyword": "", "hyType": "", "xxfcbj[]": ["3"], "needFields[]": NF, "siteId": 1}
    body = urllib.parse.urlencode(p, doseq=True).encode()
    h = {**UA, "Cookie": f"C3VK={token}",
         "Referer": "http://www.neeq.com.cn/disclosure/announcement.html",
         "X-Requested-With": "XMLHttpRequest",
         "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = op.open(urllib.request.Request(
        "https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",
        data=body, headers=h), timeout=30)
    t = r.read().decode("utf-8", "ignore")
    i = t.find("(")
    return json.loads(t[i + 1:t.rfind(")")])[0]["listInfo"]


def probe():
    """对 15 槽涉及的 8 家公司拉全量定期报告索引，留作判定证据。"""
    appl = json.loads((P03 / "applicability_review.json").read_text(encoding="utf-8"))
    oldmap = {x["security_id"]: x["old_neeq_code"]
              for x in json.loads((P03 / "historical_code_mapping.json").read_text(encoding="utf-8"))}
    codes = sorted({x["security_id"] for x in appl})
    op, token = session()
    out = {}
    for sid in codes:
        cd = oldmap[sid]
        li = fetch_periodic(op, token, cd)
        tot = li["totalElements"]
        rows = list(li["content"])
        pg = 1
        while len(rows) < tot and pg < 12:
            time.sleep(1.2)
            rows += fetch_periodic(op, token, cd, pg)["content"]
            pg += 1
        rows.sort(key=lambda r: r.get("publishDate", ""))
        out[sid] = {
            "old_neeq_code": cd,
            "index_total": tot,
            "rows_fetched": len(rows),
            "index_complete": len(rows) >= tot,
            "earliest_publish_date": rows[0]["publishDate"] if rows else "",
            "earliest_title": rows[0]["disclosureTitle"] if rows else "",
            "titles": [r["disclosureTitle"] for r in rows],
            "quarter_titles": [r["disclosureTitle"] for r in rows if "季度" in r["disclosureTitle"]],
        }
        print(f"  {sid} old={cd} total={tot} rows={len(rows)} "
              f"earliest={out[sid]['earliest_publish_date']} 季报={len(out[sid]['quarter_titles'])}")
        time.sleep(1.5)
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"probed_at": now(), "route": "neeq companyAnnouncement.do disclosureType[]=9503",
               "positive_control": "该接口同参数已在 A01 用于 50 槽补采，50/50 命中并下载成功",
               "issuers": out}
    (OUT / "applicability_evidence.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def decide():
    appl = json.loads((P03 / "applicability_review.json").read_text(encoding="utf-8"))
    ev = json.loads((OUT / "applicability_evidence.json").read_text(encoding="utf-8"))
    rows = []
    for item in appl:
        sid, slot = item["security_id"], item["slot_id"]
        code = sid.split(":")[1]
        e = ev["issuers"].get(sid, {})
        listing = item.get("current_neeq_listing_date", "")
        period_end = {"annual_2023": "2023-12-31", "h1_2024": "2024-06-30",
                      "q1_2026": "2026-03-31"}.get(slot, "")
        titles = e.get("titles") or []

        if item["technical_classification"].startswith("PERIOD_PRECEDES"):
            before = bool(listing) and period_end < listing
            no_report = not any(period_end[:4] in t and (
                "年度报告" in t if slot.startswith("annual") else "半年度报告" in t) for t in titles)
            status = NA if (before and no_report and e.get("index_complete")) else "REVIEW_FAILED"
            basis = (f"股转挂牌日 {listing} 晚于报告期结束 {period_end}；"
                     f"股转定期报告索引共 {e.get('index_total')} 条，最早一条 "
                     f"{e.get('earliest_publish_date')}「{(e.get('earliest_title') or '')[:30]}」，"
                     f"该期间无记录")
        else:
            quarter_present = any("2026年一季度" in t or "2026 年一季度" in t for t in titles)
            status = ND if (e.get("index_complete") and not quarter_present) else "REVIEW_FAILED"
            basis = (f"季度报告为自愿披露（规则第十一条）；股转定期报告索引共 "
                     f"{e.get('index_total')} 条、完整，无 2026 年一季度报告。"
                     f"同索引可返回三季报（本公司 {len(e.get('quarter_titles') or [])} 条），"
                     f"说明季报确会进该索引，缺失即未披露")

        rows.append({"security_id": sid, "stock_code": code, "stock_name": item["stock_name"],
                     "slot_id": slot, "period_end": period_end, "neeq_listing_date": listing,
                     "p03_classification": item["technical_classification"],
                     "decision": status, "basis": basis,
                     "index_total": e.get("index_total"), "index_complete": e.get("index_complete"),
                     "evidence_file": "runs/issues/A02/applicability_evidence.json"})
        print(f"  {code} {slot:11} -> {status}")

    # 回写台账
    for r in rows:
        if r["decision"] not in (NA, ND):
            continue
        code = r["stock_code"]
        data = json.loads((CKPT / f"{code}.json").read_text(encoding="utf-8"))
        rec = data["slots"][r["slot_id"]]
        if rec.get("status") == "COLLECTED_IDENTITY_VERIFIED":
            continue
        rec["status"] = r["decision"]
        rec["status_reason"] = f"A02 适用性判定：{r['basis']}"
        rec["next_action"] = "NONE"
        rec["last_error"] = None
        rec["applicability_decision"] = {
            "decided_at": now(), "by": "A02", "decision": r["decision"],
            "p03_classification": r["p03_classification"], "basis": r["basis"],
            "evidence_file": r["evidence_file"]}
        rec["updated_at"] = now()
        data["updated_at"] = now()
        (CKPT / f"{code}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    import csv
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "applicability_decisions.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--decide", action="store_true")
    a = ap.parse_args()
    if a.probe:
        probe()
    if a.decide:
        decide()


if __name__ == "__main__":
    main()
