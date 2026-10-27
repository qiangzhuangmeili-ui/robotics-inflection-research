#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A01｜集中重试失败项与备用官方来源。

只补真实失败/不完整项，不重跑已取得资料。四组缺口分别处理：

  G1  65 槽 北交所股转期未尝试  → 探测股转/北交所官方源，记全局源故障
  G2   1 槽 301622 超 80MB 上限 → 派生 config v2（120MB）后重下
  G3   5 槽 更名导致主体不匹配  → 历史简称别名表 + 本地复检
  G4   5 槽 图片版正文抽不出    → 封面位图目视确认（证据见 visual_confirmations.json）

用法：
    python tools/a01_retry.py --probe-sources
    python tools/a01_retry.py --build-config-v2
    python tools/a01_retry.py --resolve-renamed
    python tools/a01_retry.py --apply-visual
    python tools/a01_retry.py --download-oversize
    python tools/a01_retry.py --rebuild-index
    python tools/a01_retry.py --report
    python tools/a01_retry.py --all
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "runs" / "issues" / "A01"
CONFIG_V1 = ROOT / "runs" / "issues" / "P07" / "collection_config_v1.json"
CONFIG_V2 = OUT / "collection_config_v2.json"
ALIASES = ROOT / "data" / "company_name_aliases.csv"
VISUAL = OUT / "visual_confirmations.json"
CKPT = ROOT / "runs" / "collection" / "checkpoint"

VERIFIED = "COLLECTED_IDENTITY_VERIFIED"
PENDING = "COLLECTED_PENDING_IDENTITY"
FAILED = "SOURCE_FAILED"
NOT_TRIED = "NOT_TRIED"

UA = {"User-Agent": "Mozilla/5.0 (compatible; robotics-inflection-research A01 retry)"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows, fields):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_ckpt(code):
    return json.loads((CKPT / f"{code}.json").read_text(encoding="utf-8"))


def save_ckpt(code, data):
    data["updated_at"] = now()
    (CKPT / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- G1 源探测
def _opener():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))


def _cninfo_query(stock, column="szse", page=1, size=30, se="2015-01-01~2026-10-27"):
    body = urllib.parse.urlencode({
        "pageNum": page, "pageSize": size, "column": column, "tabName": "fulltext",
        "plate": "", "stock": stock, "searchkey": "", "secid": "", "category": "", "trade": "",
        "seDate": se, "sortName": "", "sortType": "", "isHLtitle": "true"}).encode()
    req = urllib.request.Request(
        "https://www.cninfo.com.cn/new/hisAnnouncement/query", data=body,
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "X-Requested-With": "XMLHttpRequest",
                 "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def _neeq_call(op, **kw):
    nf = ["companyCd", "companyName", "disclosureTitle", "disclosurePostTitle",
          "destFilePath", "publishDate", "xxfcbj", "destFilePath", "fileExt", "xxzrlx"]
    p = {"disclosureType": "", "disclosureSubtype": [], "page": "0", "companyCd": "",
         "isNewThree": "1", "startTime": "", "endTime": "", "keyword": "", "hyType": "",
         "xxfcbj": ["3"], "needFields": nf, "siteId": "1"}
    p.update(kw)
    body = urllib.parse.urlencode(p, doseq=True).encode()
    req = urllib.request.Request(
        "http://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do", data=body,
        headers={"User-Agent": "Mozilla/5.0",
                 "Referer": "http://www.neeq.com.cn/disclosure/announcement.html",
                 "X-Requested-With": "XMLHttpRequest",
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    with op.open(req, timeout=30) as r:
        txt = r.read().decode("utf-8", "ignore")
    i = txt.find("(")
    j = json.loads(txt[i + 1:txt.rfind(")")]) if i >= 0 else txt
    return j[0]["listInfo"]["totalElements"] if isinstance(j, list) and j and "listInfo" in j[0] else None


def probe_sources() -> list[dict]:
    """每条探测都记录实际请求与真实返回，不写推断。"""
    probes: list[dict] = []
    t0 = now()

    def add(group, route, target, status, result, verdict):
        probes.append({"group": group, "route": route, "target": target,
                       "http_status": status, "result": result, "verdict": verdict,
                       "probed_at": now()})

    def cninfo(stock, column="szse", page=1, size=30, se="2015-01-01~2026-10-27", tries=3):
        last = None
        for _ in range(tries):
            try:
                return _cninfo_query(stock, column, page, size, se)
            except Exception as e:  # 504 等瞬时故障重试
                last = e
                time.sleep(2)
        raise last

    # P1 巨潮股转列是否服务
    try:
        d = cninfo("830779,gfbj0830779", column="neeq")
        add("G1", "cninfo_hisAnnouncement", "column=neeq, stock=830779,gfbj0830779", "200",
            f"totalAnnouncement={d.get('totalAnnouncement')}",
            "COLUMN_NOT_SERVING" if not d.get("totalAnnouncement") else "OK")
    except Exception as e:
        add("G1", "cninfo_hisAnnouncement", "column=neeq", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    # P2 巨潮是否收录这 15 家的股转期公告（翻到最早一页）
    try:
        d = cninfo("920002,gfbj0873843", se="2015-01-01~2026-10-27")
        tot = d.get("totalAnnouncement") or 0
        last_page = (tot // 30) + 1
        d2 = cninfo("920002,gfbj0873843", page=last_page, se="2015-01-01~2026-10-27")
        rows = d2.get("announcements") or []
        oldest = rows[-1] if rows else {}
        codes = sorted({r.get("secCode") for r in rows})
        add("G1", "cninfo_hisAnnouncement", "920002 翻到最早页", "200",
            f"total={tot}; 最早={oldest.get('published_on')}; 该页secCode={codes}",
            "NO_NEEQ_ERA_ROWS" if not any(str(c).startswith("8") for c in codes) else "HAS_OLD_CODE")
    except Exception as e:
        add("G1", "cninfo_hisAnnouncement", "920002 最早页", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    # P3 对照：老股转转板的公司（920207）巨潮确有旧代码行
    try:
        d = cninfo("920207,gfbj0835207")
        tot = d.get("totalAnnouncement") or 0
        seen = set()
        for p in range(1, min(4, (tot // 30) + 2)):
            dd = cninfo("920207,gfbj0835207", page=p)
            for r in dd.get("announcements") or []:
                seen.add(r.get("secCode"))
        add("G1", "cninfo_hisAnnouncement", "920207 对照（老股转转板）", "200",
            f"total={tot}; secCodes={sorted(seen)}",
            "CNINFO_CAN_HOLD_OLD_CODE" if any(str(c).startswith("8") for c in seen) else "NO_OLD_CODE")
    except Exception as e:
        add("G1", "cninfo_hisAnnouncement", "920207 对照", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    # P4 股转官网可达性（带 cookie 会话）
    op = _opener()
    try:
        with op.open(urllib.request.Request("https://www.neeq.com.cn/", headers={"User-Agent": "Mozilla/5.0"}),
                     timeout=25) as r:
            add("G1", "neeq_official", "https 首页", r.status, "站点可达", "SITE_REACHABLE")
    except Exception as e:
        add("G1", "neeq_official", "https 首页", "ERR", f"{type(e).__name__}: {e}"[:160], "SITE_UNREACHABLE")
    try:
        op.open(urllib.request.Request("http://www.neeq.com.cn/disclosure/announcement.html",
                                       headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
    except Exception:
        pass

    # P5 股转公告接口：按年报分类
    try:
        tot = _neeq_call(op, disclosureType="1:9503-1001")
        add("G1", "neeq_official", "http companyAnnouncement.do 年报分类", "200",
            f"totalElements={tot}", "EMPTY_RESULT" if not tot else "OK")
    except Exception as e:
        add("G1", "neeq_official", "http 公告接口(年报)", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    # P5b 判别探针：最宽查询（全部类型 + 当年日期范围）也应为 0 才算数据层不可用
    try:
        tot = _neeq_call(op, disclosureType="5", startTime="2026-01-01", endTime="2026-10-27")
        add("G1", "neeq_official", "http companyAnnouncement.do 全部+日期（判别探针）", "200",
            f"totalElements={tot}", "DATA_LAYER_EMPTY" if not tot else "OK")
    except Exception as e:
        add("G1", "neeq_official", "http 公告接口(全部)", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    # P6 北交所官网
    try:
        with op.open(urllib.request.Request("https://www.bse.cn/", headers={"User-Agent": "Mozilla/5.0"}),
                     timeout=25) as r:
            add("G1", "bse_official", "https 首页", r.status, "站点可达", "SITE_REACHABLE")
    except Exception as e:
        add("G1", "bse_official", "https 首页", "ERR", f"{type(e).__name__}: {e}"[:160], "SITE_UNREACHABLE")

    # P7 巨潮股票表能否给出 8xxxxx ↔ 920xxx 的同一主体映射
    try:
        req = urllib.request.Request("https://www.cninfo.com.cn/new/data/szse_stock.json",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            lst = json.loads(r.read().decode("utf-8")).get("stockList") or []
        by_org = {}
        for x in lst:
            by_org.setdefault(x.get("orgId"), []).append(x.get("code"))
        targets = ["920002", "920011", "920022", "920055", "920060", "920066", "920080",
                   "920091", "920096", "920100", "920124", "920211", "920220", "920238", "920289"]
        mapped = {}
        for t in targets:
            hit = [x for x in lst if x.get("code") == t]
            if hit:
                oid = hit[0]["orgId"]
                mapped[t] = [c for c in by_org.get(oid, []) if c != t]
        add("G1", "cninfo_stock_list", "szse_stock.json orgId 反查旧代码", "200",
            f"股票表 {len(lst)} 行；15 家中能反查出第二代码的 {sum(1 for v in mapped.values() if v)} 家",
            "NO_OLD_CODE_MAPPING" if not any(mapped.values()) else "HAS_MAPPING")
    except Exception as e:
        add("G1", "cninfo_stock_list", "szse_stock.json", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    payload = {"generated_at": now(), "started_at": t0, "probes": probes,
               "conclusion": _probe_conclusion(probes)}
    (OUT / "source_probes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    for p in probes:
        print(f"  {p['group']} {p['route']:22} {p['verdict']:24} {p['result'][:64]}")
    print("conclusion:", payload["conclusion"]["verdict"])
    return probes


def _probe_conclusion(probes):
    """只有证据齐全才判全局不可用；否则判为未穷尽。"""
    v = {p["verdict"] for p in probes}
    if {"COLUMN_NOT_SERVING", "NO_OLD_CODE_MAPPING", "EMPTY_RESULT",
        "DATA_LAYER_EMPTY"} <= v:
        return {"verdict": "GLOBAL_SOURCE_UNAVAILABLE",
                "scope": "北交所股转挂牌期定期报告（8xxxxx 旧代码）",
                "detail": "股转官网站点可达但公告接口对最宽查询（全部类型+2026 全年）仍返 totalElements=0，"
                          "属数据层不可用；巨潮股转列不服务、这 15 家无股转期公告行（920002 最早一条为 2024-05 IPO 期）、"
                          "股票表无 8xxxxx↔920xxx 同主体映射；北交所官网可达但只覆盖上市后披露。",
                "action": "保留一个源故障请求，不拆 15 家手工公司请求；需股转数据层恢复后按 8xxxxx 旧代码检索。"}
    return {"verdict": "NOT_EXHAUSTED", "detail": "探测未覆盖全部路径，不得宣称源不可用。"}


# ---------------------------------------------------------------- G2 config v2
def build_config_v2():
    v1 = json.loads(CONFIG_V1.read_text(encoding="utf-8"))
    v2 = json.loads(CONFIG_V1.read_text(encoding="utf-8"))
    v2["config_code"] = "COLLECTION_CONFIG_V2_A01_OVERSIZE"
    v2["config_version"] = 2
    v2["derived_from"] = {"path": "runs/issues/P07/collection_config_v1.json",
                          "sha256": sha256_file(CONFIG_V1),
                          "frozen_at": v1.get("frozen_at")}
    v2["overrides"] = {
        "transport.max_download_bytes": {
            "v1": v1["transport"]["max_download_bytes"],
            "v2": 125829120,
            "reason": "301622 英思特 annual_2025 实测 87.3MB 超 80MB 上限；仅放开单份上限，不动并发/限速/重试次数",
            "authorised_by": "A00 handoff §7 / 本卡执行步骤 1-2",
        }
    }
    v2["transport"]["max_download_bytes"] = 125829120
    v2["capacity_note"] = ("单份上限 120MB 只影响单文件；P06 容量口径按槽位中位数估算，不受单份上限影响，"
                           "但极端大文件会抬高尾部字节数，已在 A01 handoff 记录。")
    v2["purpose"] = "A01 专用：放开单份下载上限以回收被 80MB 挡住的槽位；其余参数与 v1 完全一致。"
    OUT.mkdir(parents=True, exist_ok=True)
    CONFIG_V2.write_text(json.dumps(v2, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", CONFIG_V2.relative_to(ROOT), "max_download_bytes =", v2["transport"]["max_download_bytes"])


# ---------------------------------------------------------------- G3 更名
def alias_map():
    out = {}
    if not ALIASES.exists():
        return out
    for r in read_csv(ALIASES):
        out.setdefault(r["security_id"], []).append(r["alias"])
    return out


def resolve_renamed():
    from p05_collector import validate_pdf  # noqa: E402

    cfg = json.loads(CONFIG_V1.read_text(encoding="utf-8"))
    slots_cfg = {s["slot_id"]: s for s in cfg["slots"]}
    names = {r["security_id"]: r for r in read_csv(ROOT / "data/company_master.csv")}
    amap = alias_map()
    results = []
    for code in sorted({sid.split(":")[1] for sid in amap}):
        sid = f"SZ:{code}"
        data = load_ckpt(code)
        for slot_id, rec in data["slots"].items():
            if rec.get("status") != PENDING:
                continue
            doc = rec.get("document") or {}
            local = ROOT / doc.get("local_file", "")
            if not local.exists():
                results.append({"security_id": sid, "slot_id": slot_id, "result": "LOCAL_MISSING"})
                continue
            slot = dict(slots_cfg[slot_id], _selected_title=doc.get("title") or "")
            val = validate_pdf(local, slot, stock_name=names[sid]["stock_name"],
                               stock_code=code, config=cfg, aliases=amap[sid])
            ok = val.get("identity_status") == VERIFIED
            results.append({"security_id": sid, "slot_id": slot_id,
                            "issuer_match_mode": val.get("issuer_match_mode"),
                            "period_match_method": val.get("period_match_method"),
                            "identity_status": val.get("identity_status"),
                            "result": "RESOLVED" if ok else "STILL_PENDING"})
            if not ok:
                continue
            first = dict(doc.get("identity_checks") or {})
            rec["validation"] = val
            rec["status"] = VERIFIED
            rec["status_reason"] = ("A01 更名复检通过：封面主体为历史名称，经 data/company_name_aliases.csv "
                                    f"别名匹配（{val.get('issuer_match_mode')}），报告期 {val.get('period_match_method')}")
            rec["next_action"] = "NONE"
            rec["last_error"] = None
            rec["updated_at"] = now()
            doc["identity_checks_first_pass"] = first
            doc["identity_checks"] = val["checks"]
            doc["identity_checks_source"] = "validation.checks@A01"
            doc["identity_verified_via"] = "A01_ALIAS_REVALIDATION"
            doc["form"] = val.get("form")
            doc["page_count"] = val.get("page_count")
            rec["document"] = doc
        save_ckpt(code, data)
    for r in results:
        print(" ", r)
    return results


# ---------------------------------------------------------------- G4 图片版
def apply_visual():
    vis = json.loads(VISUAL.read_text(encoding="utf-8"))
    applied = []
    for it in vis["items"]:
        code = it["security_id"].split(":")[1]
        data = load_ckpt(code)
        rec = data["slots"].get(it["slot_id"])
        if not rec:
            applied.append({"security_id": it["security_id"], "slot_id": it["slot_id"],
                            "result": "SLOT_NOT_FOUND"})
            continue
        ev = ROOT / it["evidence_file"]
        if not ev.exists() or sha256_file(ev) != it["evidence_sha256"]:
            applied.append({"security_id": it["security_id"], "slot_id": it["slot_id"],
                            "result": "EVIDENCE_MISMATCH"})
            continue
        doc = rec.get("document") or {}
        first = dict(doc.get("identity_checks") or {})
        checks = dict((rec.get("validation") or {}).get("checks") or {})
        detail = f"A01 目视封面 P{it['page']}：{it['observed']}"
        checks["ISSUER_MATCH"] = {"result": "PASS",
                                  "detail": f"目视封面主体={it['issuer_full']}；证据 {it['evidence_file']}"}
        checks["PERIOD_MATCH"] = {"result": "PASS",
                                  "detail": f"目视封面报告期={it['period_phrase']}；方法=A01_VISUAL_COVER"}
        checks["FORM_FULL_TEXT"] = {"result": "PASS", "detail": "封面标注为报告全文"}
        val = dict(rec.get("validation") or {})
        val.update({"checks": checks, "identity_status": VERIFIED,
                    "identity_verified_via": "A01_VISUAL_COVER_CONFIRMATION",
                    "period_match_method": "A01_VISUAL_COVER",
                    "text_chars": val.get("text_chars", 0)})
        rec["validation"] = val
        rec["status"] = VERIFIED
        rec["status_reason"] = ("A01 目视封面确认：正文无法抽取（图片版/字形贴片），"
                                f"按 P{it['page']} 封面原句确认主体与报告期")
        rec["next_action"] = "NONE"
        rec["last_error"] = None
        rec["updated_at"] = now()
        doc["identity_checks_first_pass"] = first
        doc["identity_checks"] = checks
        doc["identity_checks_source"] = "validation.checks@A01"
        doc["identity_verified_via"] = "A01_VISUAL_COVER_CONFIRMATION"
        doc["identity_evidence"] = {"page": it["page"], "observed": it["observed"],
                                    "file": it["evidence_file"], "sha256": it["evidence_sha256"],
                                    "render_method": it["render_method"]}
        doc["form"] = "FULL_TEXT"
        rec["document"] = doc
        save_ckpt(code, data)
        applied.append({"security_id": it["security_id"], "slot_id": it["slot_id"], "result": "RESOLVED"})
    for a in applied:
        print(" ", a)
    return applied


# ---------------------------------------------------------------- G2 下载
def download_oversize():
    from p05_collector import validate_pdf  # noqa: E402
    import requests

    code, slot_id = "301622", "annual_2025"
    cfg = json.loads(CONFIG_V2.read_text(encoding="utf-8"))
    limit = int(cfg["transport"]["max_download_bytes"])
    names = {r["security_id"]: r for r in read_csv(ROOT / "data/company_master.csv")}
    sid = f"SZ:{code}"
    data = load_ckpt(code)
    rec = data["slots"][slot_id]
    doc = rec["document"]
    url = doc["primary_url"]
    target = ROOT / doc["local_file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".pdf.part")
    t0 = time.time()
    attempts = []
    try:
        with requests.get(url, headers=UA, stream=True, timeout=(8, 60)) as r:
            total = int(r.headers.get("Content-Length") or 0)
            attempts.append({"route": "cninfo_pdf_v2", "method": "GET", "url": url,
                             "http_status": r.status_code, "content_length": total,
                             "at": now()})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            if total and total > limit:
                raise RuntimeError(f"STILL_OVER_LIMIT {total} > {limit}")
            written = 0
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > limit:
                        raise RuntimeError(f"STILL_OVER_LIMIT > {limit}")
                    f.write(chunk)
        size = part.stat().st_size
        if total and size != total:
            raise RuntimeError(f"SIZE_MISMATCH {size} != {total}")
        part.replace(target)
        digest = sha256_file(target)
        attempts[-1].update({"bytes": size, "sha256": digest, "outcome": "SUCCESS",
                             "elapsed_s": round(time.time() - t0, 1)})
    except Exception as e:
        attempts[-1].update({"outcome": "ERROR", "error": f"{type(e).__name__}: {e}"[:200]})
        if part.exists():
            part.unlink()
        rec.setdefault("source_attempts", []).append(attempts[-1])
        rec["attempt_count"] = int(rec.get("attempt_count", 0)) + 1
        rec["last_error"] = str(e)[:200]
        rec["status"] = FAILED
        rec["updated_at"] = now()
        save_ckpt(code, data)
        print("  FAILED:", attempts[-1])
        return attempts

    slots_cfg = {s["slot_id"]: s for s in cfg["slots"]}
    slot = dict(slots_cfg[slot_id], _selected_title=doc.get("title") or "")
    val = validate_pdf(target, slot, stock_name=names[sid]["stock_name"], stock_code=code, config=cfg)
    ok = val.get("identity_status") == VERIFIED
    rec.setdefault("source_attempts", []).append(attempts[-1])
    rec["attempt_count"] = int(rec.get("attempt_count", 0)) + 1
    rec["last_source_attempt"] = attempts[-1]
    rec["validation"] = val
    doc.update({"sha256": digest, "bytes": target.stat().st_size,
                "page_count": val.get("page_count"), "form": val.get("form"),
                "identity_checks_first_pass": dict(doc.get("identity_checks") or {}),
                "identity_checks": val["checks"],
                "identity_checks_source": "validation.checks@A01",
                "identity_verified_via": "A01_CONFIG_V2_OVERSIZE_RETRY"})
    rec["document"] = doc
    if ok:
        rec["status"] = VERIFIED
        rec["status_reason"] = (f"A01 用 config v2（单份上限 {limit // (1024*1024)}MB）重下成功，"
                                f"{target.stat().st_size} bytes，七项校验通过")
        rec["next_action"] = "NONE"
        rec["last_error"] = None
    else:
        rec["status"] = PENDING
        rec["status_reason"] = "A01 已下载但身份校验未全通过，转待核"
        rec["next_action"] = "MANUAL_REVIEW_COVER"
    rec["updated_at"] = now()
    save_ckpt(code, data)
    print("  ", rec["status"], target.stat().st_size, "bytes", digest[:16], val.get("identity_status"))
    return attempts


# ---------------------------------------------------------------- 索引重建
def rebuild_index():
    import m00_batch  # noqa: E402
    p = m00_batch.write_shared_index()
    rows = read_csv(p)
    print("  collection_index.csv", len(rows), "rows")
    return len(rows)


# ---------------------------------------------------------------- 报告
def write_reports():
    cfg1 = json.loads(CONFIG_V1.read_text(encoding="utf-8"))
    slots_cfg = {s["slot_id"]: s for s in cfg1["slots"]}
    names = {r["security_id"]: r for r in read_csv(ROOT / "data/company_master.csv")}
    listing = {r["security_id"]: r for r in read_csv(ROOT / "data/company_listing_dates.csv")}
    probes = json.loads((OUT / "source_probes.json").read_text(encoding="utf-8"))

    attempts_rows, resolved_rows, residual_rows = [], [], []
    for f in sorted(CKPT.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        sid = data["security_id"]
        code = sid.split(":")[1]
        for slot_id, rec in sorted(data["slots"].items()):
            st = rec.get("status")
            doc = rec.get("document") or {}
            val = rec.get("validation") or {}
            checks = val.get("checks") or {}
            via = doc.get("identity_verified_via") or ""
            touched = via.startswith("A01_")
            if touched:
                attempts_rows.append({
                    "security_id": sid, "stock_code": code,
                    "stock_name": names.get(sid, {}).get("stock_name", ""),
                    "slot_id": slot_id, "prior_status": FAILED if slot_id == "annual_2025" and code == "301622" else PENDING,
                    "route": ("cninfo_pdf_config_v2" if via == "A01_CONFIG_V2_OVERSIZE_RETRY"
                              else ("local_alias_revalidation" if via == "A01_ALIAS_REVALIDATION"
                                    else "local_visual_cover")),
                    "http_issued": "YES" if via == "A01_CONFIG_V2_OVERSIZE_RETRY" else "NO",
                    "http_status": "200" if via == "A01_CONFIG_V2_OVERSIZE_RETRY" else "N/A(本地)",
                    "result": "SUCCESS" if st == VERIFIED else "PARTIAL",
                    "identity_verified_via": via,
                    "evidence": (doc.get("identity_evidence") or {}).get("observed", ""),
                    "attempted_at": rec.get("updated_at"),
                })
                if st == VERIFIED:
                    resolved_rows.append({
                        "security_id": sid, "stock_code": code,
                        "stock_name": names.get(sid, {}).get("stock_name", ""),
                        "slot_id": slot_id, "new_status": st,
                        "document_id": doc.get("document_id"),
                        "sha256": doc.get("sha256"),
                        "page_count": doc.get("page_count"),
                        "bytes": doc.get("bytes"),
                        "local_file": doc.get("local_file"),
                        "issuer_match": checks.get("ISSUER_MATCH", {}).get("result"),
                        "period_match": checks.get("PERIOD_MATCH", {}).get("result"),
                        "identity_verified_via": via,
                        "evidence": (doc.get("identity_evidence") or {}).get("observed", ""),
                        "resolved_at": rec.get("updated_at"),
                    })
            if st in (PENDING, FAILED, NOT_TRIED):
                if st == NOT_TRIED:
                    cat = "GLOBAL_SOURCE_UNAVAILABLE"
                    detail = probes["conclusion"]["detail"]
                    action = "环境恢复后按 8xxxxx 旧代码到股转官网补采；本卡不拆逐家请求"
                elif st == FAILED:
                    cat = "AUTO_EXHAUSTED"
                    detail = rec.get("last_error") or ""
                    action = "见 retry_attempts.csv 的实际返回"
                else:
                    cat = "AUTO_EXHAUSTED_NEEDS_HUMAN"
                    detail = rec.get("status_reason") or ""
                    action = "人工看封面"
                residual_rows.append({
                    "security_id": sid, "stock_code": code,
                    "stock_name": names.get(sid, {}).get("stock_name", ""),
                    "market": sid.split(":")[0], "slot_id": slot_id,
                    "report_type": rec.get("report_type"), "period_label": rec.get("period_label"),
                    "status": st, "category": cat, "detail": detail, "next_action": action,
                    "listing_date": listing.get(sid, {}).get("listing_date", ""),
                    "attempt_count": rec.get("attempt_count"),
                })

    write_csv(OUT / "retry_attempts.csv", attempts_rows,
              ["security_id", "stock_code", "stock_name", "slot_id", "prior_status", "route",
               "http_issued", "http_status", "result", "identity_verified_via", "evidence", "attempted_at"])
    write_csv(OUT / "retry_resolved.csv", resolved_rows,
              ["security_id", "stock_code", "stock_name", "slot_id", "new_status", "document_id",
               "sha256", "page_count", "bytes", "local_file", "issuer_match", "period_match",
               "identity_verified_via", "evidence", "resolved_at"])
    write_csv(OUT / "residual_failures.csv", residual_rows,
              ["security_id", "stock_code", "stock_name", "market", "slot_id", "report_type",
               "period_label", "status", "category", "detail", "next_action", "listing_date",
               "attempt_count"])
    summary = {
        "generated_at": now(),
        "attempts": len(attempts_rows),
        "resolved": len(resolved_rows),
        "residual": len(residual_rows),
        "residual_by_category": {},
        "residual_by_status": {},
    }
    for r in residual_rows:
        summary["residual_by_category"][r["category"]] = summary["residual_by_category"].get(r["category"], 0) + 1
        summary["residual_by_status"][r["status"]] = summary["residual_by_status"].get(r["status"], 0) + 1
    (OUT / "retry_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    print(" ", json.dumps(summary, ensure_ascii=False))
    return summary


def main():
    ap = argparse.ArgumentParser()
    for k in ("probe-sources", "build-config-v2", "resolve-renamed", "apply-visual",
              "download-oversize", "rebuild-index", "report", "all"):
        ap.add_argument(f"--{k}", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.all:
        for k in ("probe_sources", "build_config_v2", "resolve_renamed", "apply_visual",
                  "download_oversize", "rebuild_index", "write_reports"):
            print("==", k)
            globals()[k]()
        return
    if a.probe_sources:
        probe_sources()
    if a.build_config_v2:
        build_config_v2()
    if a.resolve_renamed:
        resolve_renamed()
    if a.apply_visual:
        apply_visual()
    if a.download_oversize:
        download_oversize()
    if a.rebuild_index:
        rebuild_index()
    if a.report:
        write_reports()


if __name__ == "__main__":
    main()
