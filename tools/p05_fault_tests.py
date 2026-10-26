"""P05 故障注入测试：不访问真实网络，全部可复算。

覆盖 issue #16 验收要求：
- 分页不完整（累计行数 != totalAnnouncement）
- HTML 伪 PDF（200 + text/html）
- 同文件重复（不同 URL 同字节）
- 下载中断与断点续传（Range 206）
- 源故障熔断（熔断后排队调用不再发请求）
以及：摘要冒充全文、主体错配、截断 PDF、北交所历史代码。

PDF 正文比对使用桩 Reader（真实字节做文件头/大小/截断判定），
真实 PDF 的可读性由 p05_live_validation.py 的三市场实跑覆盖。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import p05_collector as pc  # noqa: E402

POLICY_SRC = REPO / "runs/issues/P03/source_circuit_policy.json"
CONFIG = REPO / "runs/issues/P05/collector_config.json"

SH = pc.CompanyRef("SH:688218", "688218", "江苏北人", "SH")
SZ = pc.CompanyRef("SZ:002031", "002031", "巨轮智能", "SZ")
BJ = pc.CompanyRef("BJ:920207", "920207", "众诚科技", "BJ")

ORG_INDEX = {
    "stockList": [
        {"code": "688218", "zwjc": "江苏北人", "orgId": "gfbj0836084"},
        {"code": "002031", "zwjc": "巨轮智能", "orgId": "gssz0002031"},
        {"code": "920207", "zwjc": "众诚科技", "orgId": "gfbj0835207"},
    ]
}

ORG_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
INDEX_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_PREFIX = "https://static.cninfo.com.cn/"

# 2026-04-30 / 2025-04-30 / 2024-04-26（毫秒）
T_2025 = 1777478400000
T_2024 = 1745942400000
T_2023 = 1714060800000


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None,
                 chunks=None, drop_after=None):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self._chunks = chunks
        self._drop_after = drop_after

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def iter_content(self, chunk_size=65536):
        chunks = self._chunks if self._chunks is not None else [self.content]
        for i, chunk in enumerate(chunks):
            if self._drop_after is not None and i >= self._drop_after:
                raise requests.exceptions.ChunkedEncodingError("simulated mid-stream drop")
            yield chunk


class Router:
    def __init__(self):
        self.calls: list[dict] = []
        self.org = lambda: FakeResponse(200, ORG_INDEX)
        self.index = lambda method, url, kw: FakeResponse(200, {"announcements": [], "totalAnnouncement": 0})
        self.pdf = lambda method, url, kw: FakeResponse(404, content=b"")

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        if url == ORG_URL:
            return self.org()
        if url == INDEX_URL:
            return self.index(method, url, kwargs)
        if url.startswith(PDF_PREFIX):
            return self.pdf(method, url, kwargs)
        raise AssertionError(f"unrouted request: {method} {url}")

    def pdf_calls(self):
        return [c for c in self.calls if c["url"].startswith(PDF_PREFIX)]

    def index_calls(self):
        return [c for c in self.calls if c["url"] == INDEX_URL]


def ann(aid, title, code, name, published, url):
    return {"announcementId": aid, "announcementTitle": title, "secCode": code,
            "secName": name, "announcementTime": published, "adjunctUrl": url}


class StubPage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class StubReader:
    text = ""
    page_count = 40
    filler = "本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者重大遗漏。" * 6

    def __init__(self, path, strict=False):
        body = StubReader.text + StubReader.filler
        self.pages = [StubPage(body) for _ in range(StubReader.page_count)]


class BrokenReader:
    def __init__(self, path, strict=False):
        raise ValueError("EOF marker not found (truncated)")


class Harness:
    """每个用例一个临时仓库根，台账/缓存/原件全部隔离。"""

    def __init__(self, router: Router, const_clock: bool = False):
        self.tmp = Path(tempfile.mkdtemp(prefix="p05_"))
        (self.tmp / "runs/issues/P03").mkdir(parents=True)
        shutil.copy2(POLICY_SRC, self.tmp / "runs/issues/P03/source_circuit_policy.json")
        self.router = router
        self.clock_value = 1000.0
        self.const_clock = const_clock

    def clock(self):
        if self.const_clock:
            return 1000.0
        self.clock_value += 2.0
        return self.clock_value

    def collector(self) -> pc.Collector:
        return pc.Collector(CONFIG, root=self.tmp, transport=self.router,
                            clock=self.clock, sleeper=lambda s: None)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def pdf_bytes(size=30000, marker=b"PDF"):
    head = b"%PDF-1.7\n" + marker + b"\n"
    body = bytes((i % 251) for i in range(size - len(head)))
    return head + body


def patch_reader(reader_cls):
    original = pc.PdfReader
    pc.PdfReader = reader_cls
    return original


def make_index(total, pages):
    """pages: list[list[row]]"""
    state = {"page": 0}

    def handler(method, url, kw):
        params = kw.get("data") or {}
        page = int(params.get("pageNum", 1))
        rows = pages[page - 1] if page - 1 < len(pages) else []
        return FakeResponse(200, {"announcements": rows, "totalAnnouncement": total,
                                  "totalpages": 2, "hasMore": True})
    return handler


# ---------------------------------------------------------------- 用例


def t01_pagination_incomplete() -> dict:
    router = Router()
    rows = [ann(i, "2025年年度报告" if i == 1 else "2024年年度报告", "688218", "江苏北人", T_2025,
                f"finalpage/2026-04-30/{i}.PDF") for i in range(1, 9)]
    router.index = make_index(10, [rows[:4], rows[4:8], []])
    h = Harness(router)
    original = patch_reader(StubReader)
    StubReader.text = "江苏北人智能制造科技股份有限公司 2025年年度报告"
    try:
        result = h.collector().run([SH], ["annual_2025"])
        slot = result["companies"][0]["slots"][0]
        index = json.loads((h.tmp / "runs/issues/P05/checkpoint/688218.json").read_text(encoding="utf-8"))["indexes"]
        ann_index = index["category_ndbg_szsh"]
        ok = (ann_index["status"] == pc.ST_INDEX_INCOMPLETE
              and ann_index["rows_fetched"] == 8 and ann_index["total_announcement"] == 10
              and slot["status"] == pc.ST_INDEX_INCOMPLETE
              and len(router.pdf_calls()) == 0)
        return {
            "id": "T01", "name": "分页不完整被识别，不当作已检索", "result": "PASS" if ok else "FAIL",
            "detail": {"total_announcement": 10, "rows_fetched": 8, "pages_fetched": ann_index["pages_fetched"],
                       "slot_status": slot["status"], "pdf_calls": len(router.pdf_calls()),
                       "note": "totalpages=2/hasMore=True 均为假值，收集器只认 totalAnnouncement"},
            "evidence": ["checkpoint/688218.json#indexes.category_ndbg_szsh"],
        }
    finally:
        pc.PdfReader = original
        h.cleanup()


def t02_html_pseudo_pdf() -> dict:
    router = Router()
    router.index = make_index(1, [[ann(1, "2025年年度报告", "688218", "江苏北人", T_2025,
                                      "finalpage/2026-04-30/999.PDF")]])
    html = b"<html><body>404 page</body></html>" + b" " * 5000
    router.pdf = lambda m, u, k: FakeResponse(200, content=html,
                                              headers={"Content-Type": "text/html", "Content-Length": str(len(html))})
    h = Harness(router)
    try:
        result = h.collector().run([SH], ["annual_2025"])
        slot = result["companies"][0]["slots"][0]
        originals = list((h.tmp / "sources/p05_validation").rglob("*.pdf"))
        parts = list((h.tmp / "sources/p05_validation").rglob("*.part"))
        ok = (slot["status"] == pc.ST_SOURCE_FAILED and slot["last_error"] == "NON_PDF_RESPONSE"
              and not originals and not parts and len(router.pdf_calls()) == 2)
        return {
            "id": "T02", "name": "HTML 伪 PDF 拒收且不留原件", "result": "PASS" if ok else "FAIL",
            "detail": {"status": slot["status"], "last_error": slot["last_error"],
                       "http_calls": len(router.pdf_calls()), "pdf_files_kept": len(originals),
                       "part_files_kept": len(parts), "next_action": slot["next_action"]},
            "evidence": ["checkpoint/688218.json#slots.annual_2025"],
        }
    finally:
        h.cleanup()


def t03_duplicate_same_content() -> dict:
    router = Router()
    router.index = make_index(2, [[
        ann(1, "2024年年度报告", "688218", "江苏北人", T_2024, "finalpage/2025-04-30/111.PDF"),
        ann(2, "2025年年度报告", "688218", "江苏北人", T_2025, "finalpage/2026-04-30/222.PDF"),
    ]])
    same = pdf_bytes()
    router.pdf = lambda m, u, k: FakeResponse(200, content=same,
                                              headers={"Content-Length": str(len(same))})
    h = Harness(router)
    original = patch_reader(StubReader)
    StubReader.text = "江苏北人智能制造科技股份有限公司 2024年年度报告"
    try:
        result = h.collector().run([SH], ["annual_2024", "annual_2025"])
        slots = {s["slot_id"]: s for s in result["companies"][0]["slots"]}
        files = list((h.tmp / "sources/p05_validation").rglob("*.pdf"))
        ok = (slots["annual_2024"]["status"] == pc.ST_COLLECTED_VERIFIED
              and slots["annual_2025"]["status"] == pc.ST_DUPLICATE
              and len(files) == 1
              and slots["annual_2025"]["document"]["sha256"] == slots["annual_2024"]["document"]["sha256"])
        return {
            "id": "T03", "name": "同字节不同 URL 只入库一次", "result": "PASS" if ok else "FAIL",
            "detail": {"annual_2024": slots["annual_2024"]["status"], "annual_2025": slots["annual_2025"]["status"],
                       "files_on_disk": len(files),
                       "deduplicated_to": slots["annual_2025"]["checkpoint"].get("deduplicated_to")},
            "evidence": ["checkpoint/688218.json#slots.annual_2025.checkpoint"],
        }
    finally:
        pc.PdfReader = original
        h.cleanup()


def t04_interrupt_and_resume() -> dict:
    router = Router()
    router.index = make_index(1, [[ann(1, "2025年年度报告", "688218", "江苏北人", T_2025,
                                      "finalpage/2026-04-30/333.PDF")]])
    full = pdf_bytes(30000)
    state = {"fail": 2}

    def pdf_handler(method, url, kw):
        rng = (kw.get("headers") or {}).get("Range")
        if state["fail"] > 0:
            state["fail"] -= 1
            # 先写 10000 字节再断流
            return FakeResponse(200, chunks=[full[:10000]], drop_after=1,
                                headers={"Content-Length": str(len(full))})
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            body = full[start:]
            return FakeResponse(206, chunks=[body],
                                headers={"Content-Length": str(len(body)),
                                         "Content-Range": f"bytes {start}-{len(full) - 1}/{len(full)}"})
        return FakeResponse(200, chunks=[full], headers={"Content-Length": str(len(full))})

    router.pdf = pdf_handler
    h = Harness(router)
    original = patch_reader(StubReader)
    StubReader.text = "江苏北人智能制造科技股份有限公司 2025年年度报告"
    try:
        first = h.collector().run([SH], ["annual_2025"])
        slot1 = first["companies"][0]["slots"][0]
        part = list((h.tmp / "sources/p05_validation").rglob("*.part"))
        part_size = part[0].stat().st_size if part else 0

        second = h.collector().run([SH], ["annual_2025"])
        slot2 = second["companies"][0]["slots"][0]
        last = slot2["source_attempts"][-1]

        calls_before = len(router.pdf_calls())
        third = h.collector().run([SH], ["annual_2025"])
        slot3 = third["companies"][0]["slots"][0]
        calls_after = len(router.pdf_calls())

        ok = (slot1["status"] == pc.ST_SOURCE_FAILED and part_size == 10000
              and slot2["status"] == pc.ST_COLLECTED_VERIFIED
              and last.get("resumed_from") == 10000 and last.get("http_status") == 206
              and slot3["last_action"] == pc.ST_SKIPPED and calls_after == calls_before
              and slot2["document"]["sha256"] == pc.sha256_bytes(full))
        return {
            "id": "T04", "name": "下载中断保留断点，续传成功，再跑幂等跳过", "result": "PASS" if ok else "FAIL",
            "detail": {"run1_status": slot1["status"], "run1_part_bytes": part_size,
                       "run2_status": slot2["status"], "run2_resumed_from": last.get("resumed_from"),
                       "run2_http_status": last.get("http_status"),
                       "run3_status": slot3["status"]
                       ,"run3_last_action": slot3.get("last_action"), "run3_new_http_calls": calls_after - calls_before,
                       "sha256_match": slot2["document"]["sha256"] == pc.sha256_bytes(full)},
            "evidence": ["checkpoint/688218.json#slots.annual_2025.source_attempts"],
        }
    finally:
        pc.PdfReader = original
        h.cleanup()


def t05_source_failure_circuit() -> dict:
    router = Router()
    titles = ["2023年年度报告", "2024年年度报告", "2025年年度报告",
              "2024年半年度报告", "2025年半年度报告", "2026年半年度报告"]
    rows = [ann(i, t, "688218", "江苏北人", T_2025, f"finalpage/2026-04-30/{i}.PDF")
            for i, t in enumerate(titles, 1)]
    state = {"category": None}

    def index_handler(method, url, kw):
        params = kw.get("data") or {}
        cat = params.get("category")
        if cat != state["category"]:
            state["category"] = cat
        subset = [r for r in rows if ("半年度" in r["announcementTitle"]) == ("bndbg" in cat)]
        return FakeResponse(200, {"announcements": subset, "totalAnnouncement": len(subset)})

    router.index = index_handler
    router.pdf = lambda m, u, k: (_ for _ in ()).throw(requests.exceptions.ConnectionError("proxy down"))
    h = Harness(router)
    try:
        core = ["annual_2023", "annual_2024", "annual_2025", "h1_2024", "h1_2025", "h1_2026"]
        result = h.collector().run([SH], core)
        statuses = [s["status"] for s in result["companies"][0]["slots"]]
        pdf_calls = len(router.pdf_calls())
        ok = (pdf_calls == 2
              and all(s == pc.ST_SOURCE_FAILED for s in statuses)
              and result["summary"]["obtained"] == 0
              and result["circuit"]["cninfo_pdf"]["opened_at"] is not None)
        return {
            "id": "T05", "name": "源故障熔断后排队调用不再发请求", "result": "PASS" if ok else "FAIL",
            "detail": {"slots": len(statuses), "pdf_http_calls": pdf_calls,
                       "statuses": statuses, "obtained": result["summary"]["obtained"],
                       "circuit": result["circuit"]["cninfo_pdf"]},
            "evidence": ["checkpoint/688218.json", "run_log.jsonl"],
        }
    finally:
        h.cleanup()


def t06_summary_only() -> dict:
    router = Router()
    router.index = make_index(1, [[ann(1, "2025年年度报告摘要", "688218", "江苏北人", T_2025,
                                      "finalpage/2026-04-30/444.PDF")]])
    h = Harness(router)
    try:
        result = h.collector().run([SH], ["annual_2025"])
        slot = result["companies"][0]["slots"][0]
        ok = slot["status"] == pc.ST_SUMMARY_ONLY and len(router.pdf_calls()) == 0
        return {"id": "T06", "name": "摘要不得冒充全文", "result": "PASS" if ok else "FAIL",
                "detail": {"status": slot["status"], "next_action": slot["next_action"],
                           "pdf_calls": len(router.pdf_calls())},
                "evidence": ["checkpoint/688218.json#slots.annual_2025"]}
    finally:
        h.cleanup()


def t07_issuer_mismatch() -> dict:
    router = Router()
    router.index = make_index(1, [[ann(1, "2025年年度报告", "688218", "江苏北人", T_2025,
                                      "finalpage/2026-04-30/555.PDF")]])
    body = pdf_bytes()
    router.pdf = lambda m, u, k: FakeResponse(200, content=body, headers={"Content-Length": str(len(body))})
    h = Harness(router)
    original = patch_reader(StubReader)
    StubReader.text = "平安银行股份有限公司 2025年年度报告"
    try:
        result = h.collector().run([SH], ["annual_2025"])
        slot = result["companies"][0]["slots"][0]
        files = list((h.tmp / "sources/p05_validation").rglob("*.pdf"))
        ok = slot["status"] == pc.ST_IDENTITY_MISMATCH and not files
        return {"id": "T07", "name": "主体错配拒收且不留原件", "result": "PASS" if ok else "FAIL",
                "detail": {"status": slot["status"], "pdf_files_kept": len(files),
                           "issuer_check": slot.get("validation", {}).get("checks", {}).get("ISSUER_MATCH")},
                "evidence": ["checkpoint/688218.json#slots.annual_2025.validation"]}
    finally:
        pc.PdfReader = original
        h.cleanup()


def t08_bj_historical_code() -> dict:
    router = Router()
    rows = [
        ann(1, "2024年年度报告", "835207", "众诚科技", T_2024, "finalpage/2025-04-29/601.PDF"),
        ann(2, "2025年年度报告", "920207", "众诚科技", T_2025, "finalpage/2026-04-27/602.PDF"),
        ann(3, "2025年年度报告", "000001", "平安银行", T_2025, "finalpage/2026-04-30/603.PDF"),
    ]
    router.index = make_index(3, [rows])
    body = pdf_bytes()
    router.pdf = lambda m, u, k: FakeResponse(200, content=body, headers={"Content-Length": str(len(body))})
    h = Harness(router)
    original = patch_reader(StubReader)
    StubReader.text = "众诚科技股份有限公司 2024年年度报告"
    try:
        result = h.collector().run([BJ], ["annual_2024"])
        slot = result["companies"][0]["slots"][0]
        data = json.loads((h.tmp / "runs/issues/P05/checkpoint/920207.json").read_text(encoding="utf-8"))
        idx = data["indexes"]["category_ndbg_szsh"]
        hist = [r for r in idx["rows"] if r.get("sec_code") == "835207"]
        rejected = idx.get("rejected_rows", [])
        ok = (slot["status"] == pc.ST_COLLECTED_VERIFIED
              and idx["column"] == "szse"
              and len(hist) == 1 and len(rejected) == 1
              and rejected[0]["sec_code"] == "000001")
        return {"id": "T08", "name": "北交所历史代码接受、异主体行拒收", "result": "PASS" if ok else "FAIL",
                "detail": {"status": slot["status"], "column": idx["column"],
                           "historical_code_rows": len(hist), "rejected_rows": len(rejected),
                           "rejected_code": rejected[0]["sec_code"] if rejected else None},
                "evidence": ["checkpoint/920207.json#indexes.category_ndbg_szsh"]}
    finally:
        pc.PdfReader = original
        h.cleanup()


def t09_truncated_pdf() -> dict:
    router = Router()
    router.index = make_index(1, [[ann(1, "2025年年度报告", "688218", "江苏北人", T_2025,
                                      "finalpage/2026-04-30/666.PDF")]])
    body = pdf_bytes()[:15000]  # 头部正确但被截断
    router.pdf = lambda m, u, k: FakeResponse(200, content=body, headers={"Content-Length": str(len(body))})
    h = Harness(router)
    original = patch_reader(BrokenReader)
    try:
        result = h.collector().run([SH], ["annual_2025"])
        slot = result["companies"][0]["slots"][0]
        files = list((h.tmp / "sources/p05_validation").rglob("*.pdf"))
        ok = (slot["status"] == pc.ST_SOURCE_FAILED and slot["last_error"] == pc.VD_UNREADABLE
              and slot["next_action"] == "RETRY_DOWNLOAD" and not files)
        return {"id": "T09", "name": "截断 PDF 不计成功、可重下", "result": "PASS" if ok else "FAIL",
                "detail": {"status": slot["status"], "last_error": slot["last_error"],
                           "next_action": slot["next_action"], "pdf_files_kept": len(files)},
                "evidence": ["checkpoint/688218.json#slots.annual_2025.validation"]}
    finally:
        pc.PdfReader = original
        h.cleanup()


def t10_rate_limit_and_budget() -> dict:
    router = Router()
    router.index = make_index(1, [[ann(1, "2025年年度报告", "688218", "江苏北人", T_2025,
                                      "finalpage/2026-04-30/777.PDF")]])
    body = pdf_bytes()
    router.pdf = lambda m, u, k: FakeResponse(200, content=body, headers={"Content-Length": str(len(body))})
    h = Harness(router, const_clock=True)
    original = patch_reader(StubReader)
    StubReader.text = "江苏北人智能制造科技股份有限公司 2025年年度报告"
    try:
        collector = h.collector()
        collector.run([SH], ["annual_2025"])
        cfg = collector.config
        waits = collector.http.waits
        www = [w for w in waits if w["host"] == "www.cninfo.com.cn"]
        static_host = [w for w in waits if w["host"] == "static.cninfo.com.cn"]
        interval = float(cfg["transport"]["min_interval_per_host_seconds"])
        repeated = [w for w in waits if w["gap_from_prev_seconds"] is not None]
        ok = (cfg["transport"]["concurrency"] == 1
              and cfg["transport"]["max_http_attempts_per_request"] == 2
              and cfg["transport"]["max_slot_attempts"] == 3
              and len(www) >= 2 and www[1]["waited_seconds"] == interval
              and len(static_host) >= 1
              and all(w["waited_seconds"] == interval for w in repeated))
        return {"id": "T10", "name": "低并发/限速/重试预算参数生效", "result": "PASS" if ok else "FAIL",
                "detail": {"concurrency": cfg["transport"]["concurrency"],
                           "max_http_attempts_per_request": cfg["transport"]["max_http_attempts_per_request"],
                           "max_slot_attempts": cfg["transport"]["max_slot_attempts"],
                           "min_interval_seconds": interval,
                           "throttle_events": len(waits),
                           "www_cninfo_waits": [w["waited_seconds"] for w in www],
                           "static_cninfo_waits": [w["waited_seconds"] for w in static_host]},
                "evidence": ["collector_config.json#transport"]}
    finally:
        pc.PdfReader = original
        h.cleanup()


TESTS = [t01_pagination_incomplete, t02_html_pseudo_pdf, t03_duplicate_same_content,
         t04_interrupt_and_resume, t05_source_failure_circuit, t06_summary_only,
         t07_issuer_mismatch, t08_bj_historical_code, t09_truncated_pdf, t10_rate_limit_and_budget]


def main() -> int:
    results = []
    for fn in TESTS:
        try:
            results.append(fn())
        except Exception as exc:  # 用例异常也是失败，不掩盖
            import traceback
            results.append({"id": fn.__name__, "name": fn.__name__, "result": "FAIL",
                            "detail": {"exception": f"{type(exc).__name__}: {exc}",
                                       "trace": traceback.format_exc()[-1200:]}})
    passed = sum(1 for r in results if r["result"] == "PASS")
    payload = {
        "plan_version": pc.PLAN_VERSION,
        "issue_key": "P05",
        "generated_at": pc.utc_now(),
        "mode": "OFFLINE_FAULT_INJECTION",
        "network_used": False,
        "summary": {"total": len(results), "pass": passed, "fail": len(results) - passed},
        "tests": results,
    }
    out = REPO / "runs/issues/P05/fault_tests.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in results:
        print(f"[{r['result']}] {r['id']} {r['name']}")
    print(f"total {len(results)} pass {passed} fail {len(results) - passed}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
