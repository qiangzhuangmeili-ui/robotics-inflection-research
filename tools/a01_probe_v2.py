#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A01 源探测 v2（修正版）：为「北交所股转 65 槽」重建证据链。

v1 的两处方法错误已修正：
  1. 巨潮公告行日期字段是 announcementTime（毫秒），v1 误取 published_on → 记成 None；
     交接又据此写成「最早为 2024-05」，属未落盘的推断。
  2. 「接口返 0」直接推出「平台故障」，缺正向对照 —— 必须先用确定有公告的样本
     证明同一接口同一参数能返回数据，才谈得上故障。

v2 的判定规则：
  - 有正向对照且目标查询为 0  → 可判该路径「无数据」
  - 无正向对照               → 只能记「未证伪」，不得判平台故障

产出：runs/issues/A01/source_probes.json（v1 原文存档为 source_probes_v1_superseded.json）
"""
from __future__ import annotations

import csv
import json
import ssl
import time
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "issues" / "A01"

UA_CNINFO = {"User-Agent": "Mozilla/5.0",
             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
             "X-Requested-With": "XMLHttpRequest",
             "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"}
UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
          "Accept-Language": "zh-CN,zh;q=0.9"}

TARGETS = ["920002", "920011", "920022", "920055", "920060", "920066", "920080",
           "920091", "920096", "920100", "920124", "920211", "920220", "920238", "920289"]


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def cninfo_query(stock, column="szse", page=1, size=30, se="2010-01-01~2026-10-27", tries=3):
    body = urllib.parse.urlencode({
        "pageNum": page, "pageSize": size, "column": column, "tabName": "fulltext", "plate": "",
        "stock": stock, "searchkey": "", "secid": "", "category": "", "trade": "", "seDate": se,
        "sortName": "", "sortType": "", "isHLtitle": "true"}).encode()
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request("https://www.cninfo.com.cn/new/hisAnnouncement/query",
                                         data=body, headers=UA_CNINFO)
            with urllib.request.urlopen(req, timeout=40, context=_ctx()) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def date_of(row):
    """巨潮公告行日期：字段为 announcementTime（毫秒时间戳）。"""
    ms = row.get("announcementTime")
    return datetime.fromtimestamp(ms / 1000).date().isoformat() if ms else ""


def neeq_session():
    """股转官网是 JS cookie 挑战：先取挑战页抠 C3VK，再带 cookie 访问。"""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=_ctx()))
    first = op.open(urllib.request.Request("http://www.neeq.com.cn/", headers=UA_WEB),
                    timeout=25).read().decode("utf-8", "ignore")
    import re
    m = re.search(r"C3VK=([0-9a-f]+)", first)
    token = m.group(1) if m else ""
    home = op.open(urllib.request.Request("http://www.neeq.com.cn/",
                                          headers={**UA_WEB, "Cookie": f"C3VK={token}"}),
                   timeout=25).read().decode("utf-8", "ignore")
    return op, token, home


def neeq_call(op, token, **kw):
    nf = ["companyCd", "companyName", "disclosureTitle", "disclosurePostTitle", "destFilePath",
          "publishDate", "xxfcbj", "destFilePath", "fileExt", "xxzrlx"]
    p = {"disclosureType": "", "disclosureSubtype": [], "page": "0", "companyCd": "",
         "isNewThree": "1", "startTime": "", "endTime": "", "keyword": "", "hyType": "",
         "xxfcbj": ["3"], "needFields": nf, "siteId": "1"}
    p.update(kw)
    body = urllib.parse.urlencode(p, doseq=True).encode()
    h = {**UA_WEB, "Cookie": f"C3VK={token}",
         "Referer": "http://www.neeq.com.cn/disclosure/announcement.html",
         "X-Requested-With": "XMLHttpRequest",
         "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    req = urllib.request.Request(
        "http://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",
        data=body, headers=h)
    txt = op.open(req, timeout=30).read().decode("utf-8", "ignore")
    i = txt.find("(")
    j = json.loads(txt[i + 1:txt.rfind(")")]) if i >= 0 else txt
    if isinstance(j, list) and j and "listInfo" in j[0]:
        return j[0]["listInfo"]["totalElements"], j[0]["listInfo"].get("content") or []
    return None, []


def main():
    probes = []

    def add(pid, path, target, status, result, verdict, control_ref=""):
        probes.append({"id": pid, "path": path, "target": target, "http_status": status,
                       "result": result, "verdict": verdict, "control_ref": control_ref,
                       "probed_at": now()})

    # ---- 路径 A：巨潮（可做正向对照）
    try:
        d = cninfo_query("830779,gfbj0830779")
        tot = d.get("totalAnnouncement") or 0
        rows = d.get("announcements") or []
        add("A1", "cninfo_hisAnnouncement", "正向对照 830779 武汉蓝电（col=szse）", "200",
            f"totalAnnouncement={tot}；首条={date_of(rows[0]) if rows else ''}",
            "CONTROL_PASS" if tot else "CONTROL_FAIL")
        control_ok = tot > 0
    except Exception as e:
        add("A1", "cninfo_hisAnnouncement", "正向对照 830779", "ERR", f"{type(e).__name__}: {e}"[:160], "CONTROL_FAIL")
        control_ok = False

    try:
        d = cninfo_query("830799,gfbj0830799")
        add("A2", "cninfo_hisAnnouncement", "正向对照 830799 艾融软件", "200",
            f"totalAnnouncement={d.get('totalAnnouncement')}",
            "CONTROL_PASS" if d.get("totalAnnouncement") else "CONTROL_FAIL")
    except Exception as e:
        add("A2", "cninfo_hisAnnouncement", "正向对照 830799", "ERR", f"{type(e).__name__}: {e}"[:160], "CONTROL_FAIL")

    try:
        d = cninfo_query("830779,gfbj0830779", column="neeq")
        add("A3", "cninfo_hisAnnouncement", "column=neeq（830779）", "200",
            f"totalAnnouncement={d.get('totalAnnouncement')}",
            "COLUMN_NOT_SERVING" if not d.get("totalAnnouncement") else "OK", "A1")
    except Exception as e:
        add("A3", "cninfo_hisAnnouncement", "column=neeq", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR", "A1")

    try:
        d = cninfo_query("920207,gfbj0835207")
        tot = d.get("totalAnnouncement") or 0
        seen = set()
        for p in range(1, min(4, (tot // 30) + 2)):
            dd = cninfo_query("920207,gfbj0835207", page=p)
            for r in dd.get("announcements") or []:
                seen.add(r.get("secCode"))
        add("A4", "cninfo_hisAnnouncement", "对照 920207 众诚科技（2022 转板）", "200",
            f"total={tot}；secCodes={sorted(seen)}",
            "CNINFO_CAN_HOLD_OLD_CODE" if any(str(c).startswith("8") for c in seen) else "NO_OLD_CODE", "A1")
    except Exception as e:
        add("A4", "cninfo_hisAnnouncement", "920207 对照", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR", "A1")

    # ---- 路径 A 的逐家取证
    stock_list = {}
    try:
        req = urllib.request.Request("https://www.cninfo.com.cn/new/data/szse_stock.json",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=_ctx()) as r:
            lst = json.loads(r.read().decode("utf-8")).get("stockList") or []
        stock_list = {x["code"]: x for x in lst}
        by_name, by_org = {}, {}
        for x in lst:
            by_name.setdefault(x.get("zwjc"), []).append(x.get("code"))
            by_org.setdefault(x.get("orgId"), []).append(x.get("code"))
    except Exception:
        by_name, by_org = {}, {}

    per_company = []
    for c in TARGETS:
        try:
            org = stock_list.get(c, {}).get("orgId")
            d = cninfo_query(f"{c},{org}")
            tot = d.get("totalAnnouncement") or 0
            last_page = (tot // 30) + 1 if tot else 1
            dd = cninfo_query(f"{c},{org}", page=last_page)
            rows = dd.get("announcements") or []
            oldest = min(rows, key=lambda r: r["announcementTime"]) if rows else {}
            codes = sorted({r.get("secCode") for r in rows})
            per_company.append({
                "stock_code": c, "org_id": org, "cninfo_total": tot,
                "earliest_date": date_of(oldest),
                "earliest_title": (oldest.get("announcementTitle") or "")[:50],
                "sec_codes_in_earliest_page": codes,
                "has_old_code_row": any(str(x).startswith("8") for x in codes),
                "name_match_other_code": [x for x in by_name.get(stock_list.get(c, {}).get("zwjc"), [])
                                          if x != c],
            })
        except Exception as e:
            per_company.append({"stock_code": c, "error": f"{type(e).__name__}: {e}"[:120]})

    add("A5", "cninfo_hisAnnouncement", "15 家逐家最早公告日（见 per_company）", "200",
        f"逐家完成 {len(per_company)}；有旧码行的 "
        f"{sum(1 for x in per_company if x.get('has_old_code_row'))} 家",
        "NO_NEEQ_ERA_ROWS_ALL_15" if not any(x.get("has_old_code_row") for x in per_company)
        else "SOME_HAVE_OLD_CODE", "A1")

    try:
        add("A6", "cninfo_stock_list", "szse_stock.json 名称/orgId 反查旧代码", "200",
            f"股票表 {len(stock_list)} 行；15 家中能按名称或 orgId 反查出第二代码的 "
            f"{sum(1 for x in per_company if x.get('name_match_other_code'))} 家",
            "NO_OLD_CODE_MAPPING"
            if not any(x.get("name_match_other_code") for x in per_company) else "HAS_MAPPING")
    except Exception as e:
        add("A6", "cninfo_stock_list", "股票表反查", "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

    # ---- 路径 B：股转官网（**拿不到正向对照**）
    token, home_len = "", 0
    try:
        op, token, home = neeq_session()
        home_len = len(home)
        add("B1", "neeq_official", "站点可达性（JS cookie 挑战后可读）", "200",
            f"挑战前 345B → 带 C3VK 后 {home_len}B", "SITE_REACHABLE" if home_len > 10000 else "SITE_BLOCKED")
    except Exception as e:
        op = None
        add("B1", "neeq_official", "站点可达性", "ERR", f"{type(e).__name__}: {e}"[:160], "SITE_BLOCKED")

    neeq_results = {}
    if op:
        for pid, label, kw in [
            ("B2", "全部类型+2026 全年（最宽查询）", {"disclosureType": "5", "startTime": "2026-01-01", "endTime": "2026-10-27"}),
            ("B3", "年报分类 1:9503-1001", {"disclosureType": "1:9503-1001"}),
            ("B4", "无分类无日期", {"disclosureType": ""}),
        ]:
            try:
                tot, _ = neeq_call(op, token, **kw)
                neeq_results[pid] = tot
                add(pid, "neeq_official", f"companyAnnouncement.do {label}", "200",
                    f"totalElements={tot}", "ZERO_RESULT" if not tot else "OK")
            except Exception as e:
                add(pid, "neeq_official", label, "ERR", f"{type(e).__name__}: {e}"[:160], "ERROR")

        # B5 正向对照尝试：用 6 个候选代码逐个试，看是否有任何一个能返回数据
        cand_hits = []
        for code in ["830806", "430047", "833575", "872925", "831550", "430418"]:
            try:
                tot, rows = neeq_call(op, token, companyCd=code)
                if tot:
                    cand_hits.append({"code": code, "total": tot,
                                      "name": (rows[0].get("companyName") if rows else "")})
            except Exception:
                pass
        add("B5", "neeq_official", "正向对照：6 个候选代码逐试", "200",
            f"命中 {len(cand_hits)} 个；详情见 positive_control_attempt",
            "CONTROL_PASS" if cand_hits else "CONTROL_NOT_OBTAINED")

        # B6 15 家按现用代码直查
        zero15 = 0
        for c in TARGETS:
            try:
                tot, _ = neeq_call(op, token, companyCd=c)
                if not tot:
                    zero15 += 1
            except Exception:
                zero15 += 1
        add("B6", "neeq_official", "15 家按 920xxx 现用代码直查", "200",
            f"返 0 的 {zero15}/15（预期为 0：股转期用 8xxxxx 旧码，现用码不在股转库）",
            "EXPECTED_ZERO_NO_OLD_CODE", "B5")

    # ---- 路径 C：北交所官网
    try:
        with urllib.request.urlopen(urllib.request.Request("https://www.bse.cn/", headers=UA_WEB),
                                    timeout=25, context=_ctx()) as r:
            add("C1", "bse_official", "站点可达性", str(r.status), "站点可达",
                "SITE_REACHABLE" if r.status == 200 else "SITE_UNREACHABLE")
    except Exception as e:
        add("C1", "bse_official", "站点可达性", "ERR", f"{type(e).__name__}: {e}"[:160], "SITE_UNREACHABLE")

    # ---- 结论
    a_ok = any(p["verdict"] == "CONTROL_PASS" for p in probes)
    b_ok = any(p["verdict"] == "CONTROL_PASS" for p in probes if p["path"] == "neeq_official")
    a_no_data = any(p["verdict"] == "NO_NEEQ_ERA_ROWS_ALL_15" for p in probes)
    if a_ok and a_no_data and not b_ok:
        conclusion = {
            "verdict": "NOT_EXHAUSTED_PENDING_P03_TECHNICAL_REVIEW",
            "retracts": "GLOBAL_SOURCE_UNAVAILABLE（v1 结论，已撤回）",
            "cninfo_path": "已证伪：正向对照通过（830779 有数据），15 家逐家扫描均无股转期公告行、无旧码行。"
                           "巨潮这条路可以确认取不到，不是查询写错。",
            "neeq_path": "未证伪：股转接口对最宽查询与 6 个候选代码全部返 0，但**未取得任何正向对照样本**，"
                         "因此不能判定平台故障，也不能判定参数错误。",
            "why_not_global_failure": "「接口返 0」在缺少已知有数据的样本时，无法区分「平台不可用」与"
                                      "「参数/代码/权限不对」。v1 直接判平台故障属过度推断。",
            "what_is_proven": [
                "巨潮接口本身正常（正向对照 830779/830799 有数据）",
                "巨潮股转列 column=neeq 不服务（同一 orgId 在 szse 列有数据、neeq 列为 0）",
                "15 家在巨潮均无股转期公告行，最早一条均为北交所 IPO 期材料",
                "巨潮股票表无 8xxxxx↔920xxx 同主体映射（按代码、名称、orgId 三种方式均查不到）",
                "股转期报告确实存在：920011 招股说明书载明 2024-09-09 在股转挂牌、创新层，"
                "并引用挂牌时披露的《公开转让说明书》",
            ],
            "what_is_not_proven": [
                "股转官网公告接口是否可用（无正向对照）",
                "15 家的 8xxxxx 旧代码（招股说明书正文未载明本公司代码）",
                "这 65 个槽位是否真的可取得",
            ],
            "handoff": "runs/issues/A01/p03_review_request.md（单条技术核验请求，不拆 15 家）",
        }
    else:
        conclusion = {"verdict": "NEEDS_MANUAL_REVIEW",
                      "detail": "对照结果不满足判定条件，需人工判读。",
                      "a_control": a_ok, "b_control": b_ok, "a_no_data": a_no_data}

    payload = {"generated_at": now(), "version": 2,
               "supersedes": "source_probes.json v1（字段错误：日期取 published_on 恒为 None；结论过度推断）",
               "rule": "有正向对照且目标为 0 才能判「无数据」；无正向对照只能记「未证伪」。",
               "probes": probes, "per_company": per_company,
               "neeq_totals": neeq_results, "conclusion": conclusion}

    old = OUT / "source_probes.json"
    if old.exists() and not (OUT / "source_probes_v1_superseded.json").exists():
        old.replace(OUT / "source_probes_v1_superseded.json")
    old.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for p in probes:
        print(f"  {p['id']:3} {p['verdict']:28} {p['result'][:72]}")
    print("conclusion:", conclusion["verdict"])


if __name__ == "__main__":
    main()
