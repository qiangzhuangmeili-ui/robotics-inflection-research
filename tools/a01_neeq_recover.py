#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A01 恢复补采：按 P03 技术复核给出的 50 条股转官方全文链接，自动补齐北交所股转期槽位。

前置（由 P03 完成，本脚本不重查）：
  - 接口与参数：`companyAnnouncement.do`，`disclosureType[]` / `xxfcbj[]` 带方括号
  - 15 家旧代码：runs/issues/P03/neeq_recheck_20261027/historical_code_mapping.json
  - 50 槽官方全文候选：runs/issues/P03/neeq_recheck_20261027/slot_lookup.json

本脚本只做：查幂等 → 下载 → 七项校验 → 回写共享台账。
不重查接口、不改配置阈值、不动既有 7173 已采集与 140 既有 NA。

用法：
    python tools/a01_neeq_recover.py --dry-run
    python tools/a01_neeq_recover.py --run [--limit 10]
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

P03 = ROOT / "runs/issues/P03/neeq_recheck_20261027"
OUT = ROOT / "runs/issues/A01"
CKPT = ROOT / "runs/collection/checkpoint"
CONFIG = ROOT / "runs/issues/P07/collection_config_v1.json"

VERIFIED = "COLLECTED_IDENTITY_VERIFIED"
PENDING = "COLLECTED_PENDING_IDENTITY"
FAILED = "SOURCE_FAILED"
NOT_TRIED = "NOT_TRIED"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept-Language": "zh-CN,zh;q=0.9"}
MIN_INTERVAL = 3.0          # 站点限速实测：1.2s 会被 302，放宽到 3s
CONSECUTIVE_FAIL_STOP = 5   # 连续失败阈值
COOLDOWN_SECONDS = 90       # 触阈值后冷却再续跑
MAX_COOLDOWNS = 3           # 冷却次数上限，超过则整轮停止
BACKOFF = (5, 15)           # 单槽重试退避（秒）


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def doc_id_of(identity_key: str) -> str:
    return "DOC-" + hashlib.sha256(identity_key.encode()).hexdigest()[:16].upper()


def load_ckpt(code: str) -> dict:
    return json.loads((CKPT / f"{code}.json").read_text(encoding="utf-8"))


def save_ckpt(code: str, data: dict) -> None:
    data["updated_at"] = now()
    (CKPT / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


class Session:
    """股转官网是 JS cookie 挑战：GET 首页 → 抠 C3VK → 带 cookie 访问。"""

    def __init__(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=ctx))
        self.token = ""
        self.refresh()

    def refresh(self, tries: int = 3):
        """取 C3VK 会话令牌。站点会限速，这里必须容错重试。"""
        last = None
        for i in range(tries):
            try:
                body = self.op.open(
                    urllib.request.Request("http://www.neeq.com.cn/", headers=UA),
                    timeout=30).read().decode("utf-8", "ignore")
                m = re.search(r"C3VK=([0-9a-f]+)", body)
                self.token = m.group(1) if m else self.token
                return self.token
            except Exception as e:
                last = e
                time.sleep(10 * (i + 1))
        raise RuntimeError(f"SESSION_REFRESH_FAILED: {type(last).__name__}: {last}"[:200])

    def get(self, url: str, timeout: int = 60) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers={**UA, "Cookie": f"C3VK={self.token}",
                                                  "Referer": "http://www.neeq.com.cn/"})
        with self.op.open(req, timeout=timeout) as r:
            return r.status, r.read()


def build_plan():
    lookup = json.loads((P03 / "slot_lookup.json").read_text(encoding="utf-8"))
    codes = {x["security_id"]: x["old_neeq_code"]
             for x in json.loads((P03 / "historical_code_mapping.json").read_text(encoding="utf-8"))}
    plan = []
    for row in lookup:
        if not row.get("candidate_count"):
            continue
        sid = row["security_id"]
        code = sid.split(":")[1]
        cand = sorted(row["candidates"], key=lambda c: c.get("publishDate") or "")[-1]
        plan.append({
            "security_id": sid, "stock_code": code, "stock_name": row["stock_name"],
            "old_code": codes.get(sid, ""), "slot_id": row["slot_id"],
            "report_type": None, "period_label": None,
            "url": cand["official_pdf_url"], "title": cand.get("disclosureTitle", ""),
            "published_on": cand.get("publishDate", ""),
        })
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not (a.run or a.dry_run):
        ap.error("need --run or --dry-run")

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    slot_cfg = {s["slot_id"]: s for s in cfg["slots"]}
    names = {r["security_id"]: r for r in _csv(ROOT / "data/company_master.csv")}

    from p05_collector import validate_pdf  # noqa: E402

    plan = build_plan()
    if a.limit:
        plan = plan[:a.limit]

    log, done = [], 0
    consecutive_fail = 0
    cooldowns = 0
    sess = None
    stop_reason = ""

    for item in plan:
        sid, code, slot_id = item["security_id"], item["stock_code"], item["slot_id"]
        data = load_ckpt(code)
        rec = data["slots"][slot_id]

        # 1) 幂等：已有同哈希原件且状态已核 → 跳过，不发请求
        doc = rec.get("document") or {}
        if rec.get("status") == VERIFIED and doc.get("local_file"):
            local = ROOT / doc["local_file"]
            if local.exists() and doc.get("sha256") and sha256_file(local) == doc["sha256"]:
                log.append({"security_id": sid, "slot_id": slot_id, "action": "SKIP_ALREADY_VERIFIED"})
                continue

        if a.dry_run:
            log.append({"security_id": sid, "slot_id": slot_id, "action": "WOULD_DOWNLOAD",
                        "url": item["url"], "old_code": item["old_code"]})
            continue

        if sess is None:
            sess = Session()

        slot = dict(slot_cfg[slot_id])
        identity_key = (f"{sid}|CONSOLIDATED_LISTED_ISSUER|{slot['report_type']}|"
                        f"{slot['period_label']}|0")
        did = doc_id_of(identity_key)
        target = ROOT / "sources/collection/originals" / code / slot_id / f"{did}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(".pdf.part")

        status, err = None, None
        for attempt in (1, 2, 3):
            try:
                st, blob = sess.get(item["url"])
                if st != 200 or not blob.startswith(b"%PDF-"):
                    raise RuntimeError(f"BAD_RESPONSE status={st} head={blob[:8]!r}")
                part.write_bytes(blob)
                status = st
                break
            except Exception as e:
                err = f"{type(e).__name__}: {e}"[:200]
                if attempt <= len(BACKOFF):
                    # 302 多为瞬时（限速/会话过期）：退避后换会话重试
                    time.sleep(BACKOFF[attempt - 1])
                    try:
                        sess.refresh()
                    except Exception as re_err:
                        err = f"{err} | refresh: {re_err}"[:240]
        time.sleep(MIN_INTERVAL)

        if status != 200:
            consecutive_fail += 1
            rec.setdefault("source_attempts", []).append({
                "route": "neeq_official_pdf", "method": "GET", "url": item["url"],
                "http_status": None, "outcome": "ERROR", "error_code": "NEEQ_PDF_FETCH_FAILED",
                "error": err, "at": now()})
            rec["attempt_count"] = int(rec.get("attempt_count", 0)) + 1
            rec["status"] = FAILED
            rec["status_reason"] = "A01 恢复补采：股转官方全文链接下载失败（非公司未披露）"
            rec["last_error"] = err
            rec["next_action"] = "RETRY_AFTER_BACKOFF_OR_MANUAL_BROWSER"
            save_ckpt(code, data)
            log.append({"security_id": sid, "slot_id": slot_id, "action": "DOWNLOAD_FAILED", "error": err})
            if consecutive_fail >= CONSECUTIVE_FAIL_STOP:
                cooldowns += 1
                if cooldowns > MAX_COOLDOWNS:
                    stop_reason = f"{CONSECUTIVE_FAIL_STOP} 次连续下载失败，已冷却 {MAX_COOLDOWNS} 次仍失败，整轮停止"
                    break
                print(f"  [熔断] 连续 {consecutive_fail} 次失败，冷却 {COOLDOWN_SECONDS}s 后继续"
                      f"（第 {cooldowns}/{MAX_COOLDOWNS} 次）")
                time.sleep(COOLDOWN_SECONDS)
                sess.refresh()
                consecutive_fail = 0
            continue

        consecutive_fail = 0
        part.replace(target)
        digest = sha256_file(target)
        slot_ctx = dict(slot, _selected_title=item["title"])
        val = validate_pdf(target, slot_ctx, stock_name=names[sid]["stock_name"],
                           stock_code=code, config=cfg, aliases=[item["old_code"]])

        first = dict(doc.get("identity_checks") or {})
        rec["validation"] = val
        rec.setdefault("source_attempts", []).append({
            "route": "neeq_official_pdf", "method": "GET", "url": item["url"],
            "http_status": 200, "outcome": "SUCCESS", "bytes": target.stat().st_size,
            "sha256": digest, "at": now()})
        rec["attempt_count"] = int(rec.get("attempt_count", 0)) + 1
        rec["last_source_attempt"] = rec["source_attempts"][-1]
        rec["document"] = {
            "document_id": did, "identity_key": identity_key, "revision_no": 0,
            "source_type": "NEEQ_OFFICIAL_PDF", "title": item["title"],
            "published_on": item["published_on"], "primary_url": item["url"],
            "local_file": str(target.relative_to(ROOT)).replace("\\", "/"),
            "sha256": digest, "bytes": target.stat().st_size,
            "page_count": val.get("page_count"), "form": val.get("form"),
            "old_neeq_code": item["old_code"],
            "identity_checks_first_pass": first,
            "identity_checks": val["checks"],
            "identity_checks_source": "validation.checks@A01_NEEQ_RECOVERY",
            "identity_verified_via": "A01_NEEQ_RECOVERY_OLD_CODE",
        }
        if val.get("identity_status") == VERIFIED:
            rec["status"] = VERIFIED
            rec["status_reason"] = (f"A01 恢复补采：股转官方全文（旧码 {item['old_code']}），"
                                    f"{target.stat().st_size} bytes，七项校验通过")
            rec["next_action"] = "NONE"
            rec["last_error"] = None
            done += 1
        else:
            rec["status"] = PENDING
            rec["status_reason"] = "A01 恢复补采：已下载但身份/报告期未全通过，转待核"
            rec["next_action"] = "MANUAL_REVIEW_COVER"
        rec["updated_at"] = now()
        save_ckpt(code, data)
        log.append({"security_id": sid, "slot_id": slot_id,
                    "action": "RESOLVED" if rec["status"] == VERIFIED else "PENDING",
                    "bytes": target.stat().st_size, "identity": val.get("identity_status"),
                    "issuer_mode": val.get("issuer_match_mode"),
                    "period_method": val.get("period_match_method")})
        print(f"  {sid} {slot_id:11} {rec['status']:30} {target.stat().st_size:>9}B "
              f"{val.get('issuer_match_mode')}/{val.get('period_match_method')}")

    if not a.dry_run:
        summary = {
            "run_at": now(), "attempted": len([x for x in log if x["action"] != "SKIP_ALREADY_VERIFIED"]),
            "resolved": sum(1 for x in log if x["action"] == "RESOLVED"),
            "pending": sum(1 for x in log if x["action"] == "PENDING"),
            "failed": sum(1 for x in log if x["action"] == "DOWNLOAD_FAILED"),
            "skipped": sum(1 for x in log if x["action"] == "SKIP_ALREADY_VERIFIED"),
            "circuit_stop": stop_reason or None,
            "entries": log,
        }
        (OUT / "neeq_recovery_log.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in summary.items() if k != "entries"}, ensure_ascii=False))
    else:
        print(json.dumps({"would_download": len(log)}, ensure_ascii=False))


def _csv(p: Path):
    import csv
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    main()
