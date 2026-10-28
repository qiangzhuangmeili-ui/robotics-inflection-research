#!/usr/bin/env python
"""A04R 北交所挂牌期季度槽适用性判定。

背景：北交所公司在上市前于股转系统挂牌，挂牌期间定期报告存在但平台不同。
P05 采集器在 cninfo 目录查不到该期记录时只能记 NOT_TRIED（禁止因平台不同判不适用），
A04 的 AC05 要求 NOT_TRIED=0，因此必须逐家取证。

判定口径沿用 A02（`tools/a02_applicability.py`）：
  A. 报告期结束日早于该公司股转索引最早一条披露日 → NOT_APPLICABLE_PRE_LISTING
  B. 股转索引完整、无该期季度记录，且季度披露为自愿（现行《挂牌公司信息披露规则》第十一条）
     → NOT_DISCLOSED_BY_ISSUER
  C. 股转索引有该期季度报告 → 下载原件并校验，记 COLLECTED_IDENTITY_VERIFIED（platform=NEEQ）

用法：
    python tools/a04r_bj_applicability.py --probe     # 拉股转定期报告索引并落证据
    python tools/a04r_bj_applicability.py --decide    # 依据证据判定并回写台账
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import p05_collector as P05  # noqa: E402

OUT = ROOT / "runs/issues/A04R"
P03 = ROOT / "runs/issues/P03/neeq_recheck_20261027"
CKPT = ROOT / "runs/collection/checkpoint"
CONFIG = ROOT / "runs/issues/A01/collection_config_v2.json"
TARGET = ["q1_2024", "q3_2024", "q1_2025", "q3_2025", "q3_2026"]

NA = "NOT_APPLICABLE_PRE_LISTING"
ND = "NOT_DISCLOSED_BY_ISSUER"
VERIFIED = "COLLECTED_IDENTITY_VERIFIED"
PENDING = "COLLECTED_PENDING_IDENTITY"
FAILED = "SOURCE_FAILED"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept-Language": "zh-CN,zh;q=0.9"}
NF = ["companyCd", "companyName", "disclosureTitle", "disclosurePostTitle", "destFilePath",
      "publishDate", "xxfcbj", "fileExt", "xxzrlx"]
MIN_INTERVAL = 3.0
BACKOFF = (5, 15)
Q1 = re.compile(r"(20\d{2})\s*年\s*(?:第)?\s*一\s*季度报告")
Q3 = re.compile(r"(20\d{2})\s*年\s*三\s*季度报告")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Session:
    def __init__(self) -> None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj),
                                              urllib.request.HTTPSHandler(context=ctx))
        self.token = ""
        self.refresh()

    def refresh(self, tries: int = 3) -> str:
        last = None
        for i in range(tries):
            try:
                body = self.op.open(urllib.request.Request("http://www.neeq.com.cn/", headers=UA),
                                    timeout=30).read().decode("utf-8", "ignore")
                m = re.search(r"C3VK=([0-9a-f]+)", body)
                self.token = m.group(1) if m else self.token
                return self.token
            except Exception as exc:  # 站点限速，容错重试
                last = exc
                time.sleep(10 * (i + 1))
        raise RuntimeError(f"SESSION_REFRESH_FAILED: {type(last).__name__}: {last}"[:200])

    def get(self, url: str, timeout: int = 60):
        req = urllib.request.Request(url, headers={**UA, "Cookie": f"C3VK={self.token}",
                                                  "Referer": "http://www.neeq.com.cn/"})
        with self.op.open(req, timeout=timeout) as resp:
            return resp.status, resp.read()


def fetch_periodic(op, token: str, cd: str, page: int = 0) -> dict:
    params = {"noticeType[]": ["9503"], "disclosureType[]": ["9503"], "page": page,
              "companyCd": cd, "isNewThree": 1, "startTime": "2015-01-01",
              "endTime": "2026-10-25", "keyword": "", "hyType": "",
              "xxfcbj[]": ["3"], "needFields[]": NF, "siteId": 1}
    body = urllib.parse.urlencode(params, doseq=True).encode()
    headers = {**UA, "Cookie": f"C3VK={token}",
               "Referer": "http://www.neeq.com.cn/disclosure/announcement.html",
               "X-Requested-With": "XMLHttpRequest",
               "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    resp = op.open(urllib.request.Request(
        "https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",
        data=body, headers=headers), timeout=30)
    text = resp.read().decode("utf-8", "ignore")
    i = text.find("(")
    return json.loads(text[i + 1:text.rfind(")")])[0]["listInfo"]


def bj_cases() -> list[dict]:
    codes = {x["security_id"]: x["old_neeq_code"]
             for x in json.loads((P03 / "historical_code_mapping.json").read_text(encoding="utf-8"))}
    scope = json.loads((ROOT / "runs/issues/P00/collection_scope.json").read_text(encoding="utf-8"))
    period_end = {s["slot_id"]: s["period_end"] for s in scope["report_slots"] + scope["quarterly_slots"]}
    out = []
    for p in sorted(CKPT.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        sid = data.get("security_id") or ""
        if not sid.startswith("BJ"):
            continue
        for slot in TARGET:
            rec = (data.get("slots") or {}).get(slot)
            if not rec or rec.get("status") != "NOT_TRIED":
                continue
            out.append({"security_id": sid, "stock_code": sid.split(":")[1], "slot_id": slot,
                        "period_end": period_end[slot], "old_code": codes.get(sid, "")})
    return out


def probe() -> dict:
    cases = bj_cases()
    companies = sorted({c["security_id"] for c in cases})
    print(f"待取证北交所公司 {len(companies)}，槽位 {len(cases)}", flush=True)
    sess = Session()
    out = {}
    for sid in companies:
        cd = next(c["old_code"] for c in cases if c["security_id"] == sid)
        if not cd:
            out[sid] = {"error": "NO_OLD_CODE"}
            continue
        li = fetch_periodic(sess.op, sess.token, cd)
        total = li.get("totalElements")
        rows = list(li.get("content") or [])
        page = 1
        while len(rows) < (total or 0) and page < 12:
            time.sleep(MIN_INTERVAL)
            rows += fetch_periodic(sess.op, sess.token, cd, page).get("content") or []
            page += 1
        rows.sort(key=lambda r: r.get("publishDate") or "")
        out[sid] = {
            "old_neeq_code": cd, "index_total": total, "rows_fetched": len(rows),
            "index_complete": len(rows) >= (total or 0),
            "earliest_publish_date": rows[0].get("publishDate") if rows else "",
            "rows": [{"title": r.get("disclosureTitle"), "published_on": r.get("publishDate"),
                      "url": "https://www.neeq.com.cn" + (r.get("destFilePath") or "")} for r in rows],
        }
        print(f"  {sid} old={cd} total={total} rows={len(rows)} "
              f"earliest={out[sid]['earliest_publish_date']}", flush=True)
        time.sleep(MIN_INTERVAL)
    payload = {"probed_at": now(), "route": "neeq companyAnnouncement.do disclosureType[]=9503",
               "positive_control": "同接口同参数已在 A01 用于 50 槽补采，50/50 命中并下载成功",
               "issuers": out}
    (OUT / "neeq_quarter_evidence.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def decide() -> dict:
    ev = json.loads((OUT / "neeq_quarter_evidence.json").read_text(encoding="utf-8"))["issuers"]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    slots = {s["slot_id"]: s for s in cfg["slots"]}
    names = {r["security_id"]: r["stock_name"]
             for r in csv.DictReader(open(ROOT / "data/company_master.csv", encoding="utf-8-sig"))}
    cases = bj_cases()
    sess = None
    rows = []
    for case in cases:
        sid, slot, code = case["security_id"], case["slot_id"], case["stock_code"]
        info = ev.get(sid) or {}
        if not info or info.get("error") or not info.get("index_complete"):
            rows.append({**case, "decision": "HOLD_INDEX_INCOMPLETE", "evidence": "股转索引未取全"})
            continue
        period_year = slot.split("_")[1]
        want = Q1 if slot.startswith("q1") else Q3
        hit = None
        for r in info["rows"]:
            title = r.get("title") or ""
            if "摘要" in title or "英文" in title:
                continue
            m = want.search(title)
            if m and m.group(1) == period_year:
                hit = r
        earliest = info.get("earliest_publish_date") or ""
        path = CKPT / f"{code}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = (data.get("slots") or {}).get(slot) or {}
        if hit:
            url = hit["url"]
            identity_key = (f"{sid}|CONSOLIDATED_LISTED_ISSUER|{slots[slot]['report_type']}|"
                            f"{slots[slot]['period_label']}|0")
            document_id = "DOC-" + hashlib.sha256(identity_key.encode()).hexdigest()[:16].upper()
            target = ROOT / "sources/collection/originals" / code / slot / f"{document_id}.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(".pdf.part")
            ok = False
            err = ""
            for attempt in (1, 2, 3):
                try:
                    if sess is None:
                        sess = Session()
                    st, blob = sess.get(url)
                    if st != 200 or not blob.startswith(b"%PDF-"):
                        raise RuntimeError(f"BAD_RESPONSE status={st} head={blob[:8]!r}")
                    part.write_bytes(blob)
                    ok = True
                    break
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"[:200]
                    time.sleep(BACKOFF[attempt - 1])
                    try:
                        sess.refresh()
                    except Exception:
                        pass
            time.sleep(MIN_INTERVAL)
            if ok:
                part.replace(target)
                slot_ctx = dict(slots[slot], _selected_title=hit["title"])
                val = P05.validate_pdf(target, slot_ctx, stock_name=names.get(sid, ""),
                                       stock_code=code, config=cfg, aliases=[case["old_code"]])
                rec.update({
                    "status": val["identity_status"],
                    "status_reason": ("A04R 北交所挂牌期季度报告：股转官方全文，主体/报告期校验通过"
                                      if val["identity_status"] == VERIFIED
                                      else "股转原件已取得但正文抽取不足，待人工看封面"),
                    "next_action": "NONE" if val["identity_status"] == VERIFIED else "MANUAL_IDENTITY_CHECK",
                    "document": {"document_id": document_id, "title": hit["title"],
                                 "published_on": hit["published_on"], "primary_url": url,
                                 "sha256": sha256_file(target), "bytes": target.stat().st_size,
                                 "page_count": val.get("page_count"), "form": val.get("form"),
                                 "local_file": target.relative_to(ROOT).as_posix(),
                                 "platform": "NEEQ", "identity_checks": val["checks"]},
                    "validation": val, "updated_at": now(),
                    "source_attempts": (rec.get("source_attempts") or []) + [{
                        "route": "neeq_official_pdf", "method": "GET", "url": url,
                        "http_status": 200, "outcome": "SUCCESS",
                        "bytes": target.stat().st_size, "at": now()}],
                    "attempt_count": int(rec.get("attempt_count") or 0) + 1,
                })
                rows.append({**case, "decision": val["identity_status"], "evidence": url})
            else:
                rec.update({"status": FAILED, "status_reason": f"A04R 股转季度报告下载失败：{err}",
                            "next_action": "RETRY_AFTER_BACKOFF", "updated_at": now()})
                rows.append({**case, "decision": "DOWNLOAD_FAILED", "evidence": err})
        elif earliest and earliest > case["period_end"]:
            rec.update({
                "status": NA,
                "status_reason": (f"A04R 股转索引最早一条 {earliest} 晚于报告期结束 {case['period_end']}，"
                                  "公司当时未在股转挂牌"),
                "next_action": "NONE", "reason_code": "NEEQ_LISTING_AFTER_PERIOD_END",
                "updated_at": now(),
            })
            rows.append({**case, "decision": NA, "evidence": f"earliest_neeq_publish={earliest}"})
        else:
            rec.update({
                "status": ND,
                "status_reason": ("A04R 股转定期报告索引完整但无该期季度报告；现行《挂牌公司信息披露规则》"
                                  "第十一条季度报告为自愿披露，同索引可返回他司季报，缺失即未披露"),
                "next_action": "NONE", "reason_code": "NEEQ_VOLUNTARY_QUARTER_NOT_DISCLOSED",
                "updated_at": now(),
            })
            rows.append({**case, "decision": ND,
                         "evidence": f"index_total={info['index_total']}, no {slot} row"})
        data["slots"][slot] = rec
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (OUT / "neeq_slot_decisions.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                           ["security_id", "stock_code", "slot_id", "period_end", "old_code", "decision", "evidence"])
        w.writeheader()
        w.writerows(rows)
    summary = {"decided": len(rows),
               "by_decision": {k: sum(1 for r in rows if r["decision"] == k)
                               for k in sorted({r["decision"] for r in rows})}}
    (OUT / "neeq_slot_decisions.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--decide", action="store_true")
    args = ap.parse_args()
    if args.probe:
        probe()
    if args.decide:
        decide()
    if not (args.probe or args.decide):
        print(json.dumps({"pending_bj_slots": len(bj_cases())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
