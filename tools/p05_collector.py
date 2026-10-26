"""P05 可断点续跑的公告/定期报告采集器与下载校验。

对应 issue #16 的四条要求：
1. 公告全分页 + 上游 totalAnnouncement 核对，保留原始响应、请求参数、来源时间与游标。
2. 每个 (security_id, slot_id) 记录 source_attempt / attempt_count / last_error / next_action / checkpoint，
   已取得原件时幂等跳过且不发出 HTTP 请求。
3. 原文校验：HTTP / 文件头 / PDF 可读 / 标题主体报告期 / 页数 / SHA256；链接记录不算下载成功。
4. 低并发、按主机限速、重试预算、按源熔断、中断恢复；北交所与历史代码是独立用例。

本模块不跑全池、不做业务判断、不改任何原始输入。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import requests

try:  # PDF 可读性校验
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from source_access import Circuit, CircuitOpen, DocumentUnavailable, SourceFailure  # noqa: E402

CONFIG_PATH = ROOT / "runs/issues/P05/collector_config.json"
PLAN_VERSION = "20261026_collection_first_v2"

# ---------------------------------------------------------------- 状态常量

ST_PENDING = "PENDING"
ST_IN_PROGRESS = "IN_PROGRESS"
ST_COLLECTED_VERIFIED = "COLLECTED_IDENTITY_VERIFIED"
ST_COLLECTED_PENDING = "COLLECTED_PENDING_IDENTITY"
ST_SKIPPED = "SKIPPED_ALREADY_HAVE"
ST_DUPLICATE = "DUPLICATE_SAME_CONTENT"
ST_INDEX_INCOMPLETE = "INDEX_INCOMPLETE_PAGINATION"
ST_SUMMARY_ONLY = "SUMMARY_ONLY"
ST_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
ST_NOT_DISCLOSED = "NOT_DISCLOSED_BY_ISSUER"
ST_NOT_TRIED = "NOT_TRIED"
ST_SOURCE_FAILED = "SOURCE_FAILED"
ST_ACCESS_BLOCKED = "ACCESS_BLOCKED"
ST_AFTER_CUTOFF = "AFTER_CUTOFF_DISCLOSED"
ST_NOT_APPLICABLE = "NOT_APPLICABLE_PRE_LISTING"
ST_NOT_YET_DISCLOSED = "NOT_YET_DISCLOSED"

# PDF 校验结论（内部）
VD_VERIFIED = ST_COLLECTED_VERIFIED
VD_PENDING = ST_COLLECTED_PENDING
VD_MISMATCH = ST_IDENTITY_MISMATCH
VD_UNREADABLE = "PDF_UNREADABLE"

OBTAINED_STATUSES = {ST_COLLECTED_VERIFIED, ST_COLLECTED_PENDING, ST_SKIPPED}
TERMINAL_NO_RETRY = {
    ST_COLLECTED_VERIFIED,
    ST_COLLECTED_PENDING,
    ST_SKIPPED,
    ST_DUPLICATE,
    ST_NOT_YET_DISCLOSED,
    ST_NOT_APPLICABLE,
    ST_AFTER_CUTOFF,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    """全角转半角 + 去空白，用于主体/报告期比对。"""
    if not text:
        return ""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def parse_security_id(security_id: str) -> tuple[str, str]:
    """显式 SH/SZ/BJ，不从代码前缀猜交易所。"""
    if not isinstance(security_id, str) or ":" not in security_id:
        raise ValueError("security_id 必须是 SH/SZ/BJ:6位代码")
    exchange, code = security_id.split(":", 1)
    if exchange not in ("SH", "SZ", "BJ") or len(code) != 6 or not code.isdigit():
        raise ValueError("security_id 必须是 SH/SZ/BJ:6位代码")
    return exchange, code


def ms_to_date(value: Any) -> str | None:
    try:
        ts = int(value) / 1000
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


# ---------------------------------------------------------------- 台账


class Ledger:
    """按证券分文件的槽位台账；每次写入原子替换，中断后可直接续跑。"""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}

    def _path(self, code: str) -> Path:
        return self.dir / f"{code}.json"

    def load(self, code: str) -> dict:
        if code in self._cache:
            return self._cache[code]
        path = self._path(code)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {"security_id": None, "slots": {}, "indexes": {}}
        data.setdefault("slots", {})
        data.setdefault("indexes", {})
        self._cache[code] = data
        return data

    def save(self, code: str) -> None:
        data = self._cache[code]
        data["updated_at"] = utc_now()
        path = self._path(code)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def slot(self, security_id: str, code: str, slot_id: str) -> dict | None:
        return self.load(code)["slots"].get(slot_id)

    def put_slot(self, security_id: str, code: str, record: dict) -> None:
        data = self.load(code)
        data["security_id"] = security_id
        data["slots"][record["slot_id"]] = record
        self.save(code)

    def put_index(self, security_id: str, code: str, category: str, index: dict) -> None:
        data = self.load(code)
        data["security_id"] = security_id
        data["indexes"][category] = index
        self.save(code)

    def get_index(self, code: str, category: str, ttl_seconds: int) -> dict | None:
        idx = self.load(code).get("indexes", {}).get(category)
        if not idx or not idx.get("fetched_at"):
            return None
        try:
            fetched = datetime.fromisoformat(idx["fetched_at"])
        except ValueError:
            return None
        if datetime.now(timezone.utc) - fetched > timedelta(seconds=ttl_seconds):
            return None
        return idx

    def iter_slots(self):
        for path in sorted(self.dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for slot_id, record in data.get("slots", {}).items():
                yield data.get("security_id"), slot_id, record


# ---------------------------------------------------------------- 传输层


class TransportFailure(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass
class CallRecord:
    route: str
    method: str
    url: str
    request_params: dict
    http_status: int | None
    outcome: str
    error_code: str | None
    elapsed_ms: int
    at: str
    response_sha256: str | None = None
    bytes: int | None = None
    resumed_from: int | None = None

    def as_dict(self) -> dict:
        return {
            "route": self.route,
            "method": self.method,
            "url": self.url,
            "request_params": self.request_params,
            "http_status": self.http_status,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "elapsed_ms": self.elapsed_ms,
            "at": self.at,
            "response_sha256": self.response_sha256,
            "bytes": self.bytes,
            "resumed_from": self.resumed_from,
        }


class HttpClient:
    """按主机限速 + 有限重试 + 按源熔断 + Range 续传。"""

    def __init__(
        self,
        config: dict,
        *,
        transport: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        root: Path = ROOT,
    ):
        self.cfg = config["transport"]
        self.dl = config["download"]
        self.clock = clock
        self.sleeper = sleeper
        self.root = root
        policy_path = root / self.cfg["circuit_policy_file"]
        self.policy = json.loads(policy_path.read_text(encoding="utf-8"))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.cfg["user_agent"], "Referer": "https://www.cninfo.com.cn/"})
        self.transport = transport or self.session.request
        self.states: dict[str, Circuit] = {}
        self.calls: list[CallRecord] = []
        self.waits: list[dict] = []
        self._last_host: dict[str, float] = {}

    def _state(self, route: str) -> Circuit:
        return self.states.setdefault(route, Circuit())

    def circuit_snapshot(self) -> dict:
        return {k: {"failures": v.failures, "opened_at": v.opened_at, "last_error": v.last_error}
                for k, v in self.states.items()}

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        now = self.clock()
        last = self._last_host.get(host)
        interval = float(self.cfg["min_interval_per_host_seconds"])
        waited = 0.0
        if last is not None:
            waited = max(0.0, interval - (now - last))
            if waited:
                self.sleeper(waited)
        self._last_host[host] = self.clock()
        self.waits.append({
            "host": host,
            "waited_seconds": round(waited, 3),
            "gap_from_prev_seconds": None if last is None else round(now - last, 3),
            "at": round(now, 3),
        })

    def _record(self, rec: CallRecord) -> None:
        self.calls.append(rec)

    def _open_circuit_if_needed(self, state: Circuit, code: str, threshold: int) -> None:
        state.failure(code, self.clock(), threshold)

    def request_json(self, route: str, method: str, url: str, *, request_params: dict | None = None,
                     **kwargs) -> tuple[Any, CallRecord]:
        state = self._state(route)
        if not state.allow(self.clock(), self.policy["cooldown_seconds"]):
            raise CircuitOpen(route)
        attempts = int(self.cfg["max_http_attempts_per_request"])
        last_code = "EXHAUSTED"
        for attempt in range(1, attempts + 1):
            started = self.clock()
            try:
                self._throttle(url)
                resp = self.transport(
                    method, url,
                    timeout=(self.cfg["connect_timeout_seconds"], self.cfg["read_timeout_seconds"]),
                    **kwargs,
                )
                status = getattr(resp, "status_code", None)
                if status == 404:
                    raise DocumentUnavailable("HTTP_404_DOCUMENT_ONLY")
                if status in (401, 403, 429):
                    self._open_circuit_if_needed(state, f"HTTP_{status}", 1)
                    self._record(CallRecord(route, method, url, request_params or {}, status, "ERROR",
                                            f"HTTP_{status}", int((self.clock() - started) * 1000), utc_now()))
                    raise SourceFailure(f"HTTP_{status}")
                if status != 200:
                    raise TransportFailure(f"HTTP_{status}")
                body = getattr(resp, "content", b"") or b""
                try:
                    payload = resp.json()
                except ValueError:
                    raise TransportFailure("INVALID_JSON") from None
                if not isinstance(payload, (dict, list)):
                    raise TransportFailure("INVALID_SCHEMA")
                state.success()
                rec = CallRecord(route, method, url, request_params or {}, status, "SUCCESS", None,
                                 int((self.clock() - started) * 1000), utc_now(),
                                 response_sha256=sha256_bytes(body), bytes=len(body))
                self._record(rec)
                return payload, rec
            except DocumentUnavailable as exc:
                self._record(CallRecord(route, method, url, request_params or {}, 404, "DOCUMENT_UNAVAILABLE",
                                        str(exc), int((self.clock() - started) * 1000), utc_now()))
                raise
            except SourceFailure:
                raise
            except CircuitOpen:
                raise
            except TransportFailure as exc:
                last_code = exc.code
                self._record(CallRecord(route, method, url, request_params or {}, None, "ERROR", exc.code,
                                        int((self.clock() - started) * 1000), utc_now()))
                self._open_circuit_if_needed(state, exc.code, int(self.policy["source_failure_threshold"]))
                if state.opened_at is not None:
                    raise SourceFailure(exc.code) from None
                if attempt < attempts:
                    self.sleeper(self.cfg["retry_delay_seconds"])
                    continue
                raise SourceFailure(exc.code) from None
            except requests.RequestException as exc:
                code = type(exc).__name__.upper()
                last_code = code
                self._record(CallRecord(route, method, url, request_params or {}, None, "ERROR", code,
                                        int((self.clock() - started) * 1000), utc_now()))
                self._open_circuit_if_needed(state, code, int(self.policy["transport_failure_threshold"]))
                if state.opened_at is not None:
                    raise SourceFailure(code) from None
                if attempt < attempts:
                    self.sleeper(self.cfg["retry_delay_seconds"])
                    continue
                raise SourceFailure(code) from None
        raise SourceFailure(last_code)

    def download(self, route: str, url: str, part_path: Path, *, expect_pdf: bool = False) -> tuple[dict, list[CallRecord]]:
        """流式下载到 .part，支持 Range 续传与 Content-Length 校验。"""
        state = self._state(route)
        if not state.allow(self.clock(), self.policy["cooldown_seconds"]):
            raise CircuitOpen(route)
        part_path = Path(part_path)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        attempts = int(self.cfg["max_http_attempts_per_request"])
        records: list[CallRecord] = []
        last_code = "EXHAUSTED"
        max_bytes = int(self.cfg["max_download_bytes"])

        for attempt in range(1, attempts + 1):
            resumed_from = part_path.stat().st_size if part_path.exists() else 0
            headers: dict[str, str] = {}
            if resumed_from and self.dl["resume_via_range"]:
                headers["Range"] = f"bytes={resumed_from}-"
            started = self.clock()
            try:
                self._throttle(url)
                resp = self.transport(
                    "GET", url, headers=headers,
                    timeout=(self.cfg["connect_timeout_seconds"], self.cfg["pdf_read_timeout_seconds"]),
                    stream=True,
                )
                status = getattr(resp, "status_code", None)
                if status == 404:
                    raise DocumentUnavailable("HTTP_404_DOCUMENT_ONLY")
                if status in (401, 403, 429):
                    self._open_circuit_if_needed(state, f"HTTP_{status}", 1)
                    raise SourceFailure(f"HTTP_{status}")
                if status not in (200, 206):
                    raise TransportFailure(f"HTTP_{status}")
                if status == 200 and resumed_from:
                    part_path.unlink(missing_ok=True)  # 服务端忽略 Range，必须从头写
                    resumed_from = 0
                written = resumed_from
                first_chunk = True
                with part_path.open("ab" if resumed_from else "wb") as fh:
                    if hasattr(resp, "iter_content"):
                        for chunk in resp.iter_content(chunk_size=65536):
                            if not chunk:
                                continue
                            if first_chunk and expect_pdf and resumed_from == 0 and not chunk.startswith(b"%PDF-"):
                                fh.close()
                                part_path.unlink(missing_ok=True)
                                raise TransportFailure("NON_PDF_RESPONSE")
                            first_chunk = False
                            fh.write(chunk)
                            written += len(chunk)
                            if written > max_bytes:
                                raise TransportFailure("SIZE_OVER_LIMIT")
                    else:
                        data = getattr(resp, "content", b"") or b""
                        if expect_pdf and not data.startswith(b"%PDF-"):
                            raise TransportFailure("NON_PDF_RESPONSE")
                        fh.write(data)
                        written += len(data)

                resp_headers = getattr(resp, "headers", {}) or {}
                total_expected = None
                if status == 206:
                    m = re.search(r"/(\d+)$", str(resp_headers.get("Content-Range", "")))
                    if m:
                        total_expected = int(m.group(1))
                elif resp_headers.get("Content-Length") is not None:
                    try:
                        total_expected = int(resp_headers["Content-Length"])
                    except (TypeError, ValueError):
                        total_expected = None
                if self.dl["verify_content_length"] and total_expected and written != total_expected:
                    raise TransportFailure("PARTIAL_CONTENT")
                state.success()
                rec = CallRecord(route, "GET", url, {"Range": headers.get("Range")}, status, "SUCCESS", None,
                                 int((self.clock() - started) * 1000), utc_now(),
                                 bytes=written, resumed_from=resumed_from)
                records.append(rec)
                self._record(rec)
                return {"status": "OK", "bytes": written, "resumed_from": resumed_from,
                        "sha256": sha256_file(part_path), "http_status": status}, records
            except DocumentUnavailable:
                records.append(CallRecord(route, "GET", url, {}, 404, "DOCUMENT_UNAVAILABLE", "HTTP_404",
                                          int((self.clock() - started) * 1000), utc_now()))
                self._record(records[-1])
                raise
            except SourceFailure:
                raise
            except CircuitOpen:
                raise
            except TransportFailure as exc:
                last_code = exc.code
                records.append(CallRecord(route, "GET", url, {"Range": headers.get("Range")}, None, "ERROR",
                                          exc.code, int((self.clock() - started) * 1000), utc_now(),
                                          resumed_from=resumed_from,
                                          bytes=part_path.stat().st_size if part_path.exists() else 0))
                self._record(records[-1])
                self._open_circuit_if_needed(state, exc.code, int(self.policy["source_failure_threshold"]))
                if state.opened_at is not None:
                    raise SourceFailure(exc.code) from None
                if attempt < attempts:
                    self.sleeper(self.cfg["retry_delay_seconds"])
                    continue
                raise SourceFailure(exc.code) from None
            except requests.RequestException as exc:
                code = type(exc).__name__.upper()
                last_code = code
                records.append(CallRecord(route, "GET", url, {"Range": headers.get("Range")}, None, "ERROR",
                                          code, int((self.clock() - started) * 1000), utc_now(),
                                          resumed_from=resumed_from,
                                          bytes=part_path.stat().st_size if part_path.exists() else 0))
                self._record(records[-1])
                self._open_circuit_if_needed(state, code, int(self.policy["transport_failure_threshold"]))
                if state.opened_at is not None:
                    raise SourceFailure(code) from None
                if attempt < attempts:
                    self.sleeper(self.cfg["retry_delay_seconds"])
                    continue
                raise SourceFailure(code) from None
        raise SourceFailure(last_code)


# ---------------------------------------------------------------- PDF 校验


def validate_pdf(path: Path, slot: dict, *, stock_name: str, stock_code: str, config: dict) -> dict:
    """逐项校验：文件头 / 大小 / 可打开 / 页数 / 主体 / 报告期 / 全文形态。"""
    rules = config["pdf_validation"]
    checks: dict[str, dict] = {}
    result: dict[str, Any] = {
        "path": str(path), "bytes": 0, "checks": checks, "identity_status": VD_UNREADABLE,
        "form": None, "page_count": None, "text_chars": 0, "issues": [], "sha256": None,
    }

    def add(name: str, ok: bool | None, detail: str = "") -> None:
        checks[name] = {"result": "PASS" if ok is True else ("FAIL" if ok is False else "UNKNOWN"),
                        "detail": detail}
        if ok is False:
            result["issues"].append(name)

    if not path.exists():
        add("MAGIC_HEADER", False, "文件不存在")
        return result
    result["bytes"] = path.stat().st_size
    result["sha256"] = sha256_file(path)
    with path.open("rb") as fh:
        head = fh.read(8)
    magic_ok = head.startswith(rules["magic"].encode())
    add("MAGIC_HEADER", magic_ok, head[:8].decode("latin-1", "replace"))
    add("SIZE_FLOOR", result["bytes"] >= int(rules["min_bytes"]), f"{result['bytes']} bytes")
    if not magic_ok:
        return result

    try:
        reader = PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
        result["page_count"] = page_count
        add("PDF_OPENABLE", page_count > 0, f"{page_count} pages")
        if page_count == 0:
            return result
    except Exception as exc:
        add("PDF_OPENABLE", False, f"{type(exc).__name__}: {exc}"[:200])
        return result

    min_pages = int(slot.get("min_pages", 3))
    add("PAGE_COUNT_FLOOR", page_count >= min_pages, f"{page_count} >= {min_pages}")

    probe = min(int(rules["text_pages_probe"]), page_count)
    text = ""
    for i in range(probe):
        try:
            text += reader.pages[i].extract_text() or ""
        except Exception:
            continue
    result["text_chars"] = len(text)
    norm = normalize_text(text)

    if result["text_chars"] < int(rules["min_text_chars_first_pages"]):
        add("ISSUER_MATCH", None, "正文抽取不足，无法核对主体")
        add("PERIOD_MATCH", None, "正文抽取不足，无法核对报告期")
        add("FORM_FULL_TEXT", None, "正文抽取不足，无法判断全文/摘要")
        result["identity_status"] = VD_PENDING
        return result

    name_norm = normalize_text(stock_name)
    issuer_ok = bool(name_norm) and name_norm in norm
    if not issuer_ok:
        issuer_ok = stock_code in norm
    add("ISSUER_MATCH", issuer_ok, f"证券简称={stock_name} 代码={stock_code}")

    m_year = re.search(r"(\d{4})", slot["period_label"])
    if not m_year:
        add("PERIOD_MATCH", False, f"period_label 无法解析年份：{slot['period_label']}")
        result["identity_status"] = VD_MISMATCH
        return result
    year = m_year.group(1)
    if slot["report_type"] == "ANNUAL_REPORT":
        pattern = rf"{year}年年度报告"
    elif slot["report_type"] == "SEMI_ANNUAL_REPORT":
        pattern = rf"{year}年半年度报告"
    else:
        pattern = rf"{year}年第[一三]季度报告"
    title = slot.get("_selected_title") or ""
    body_phrase = re.search(pattern, norm) is not None
    year_in_body = year in norm
    title_norm = normalize_text(title)
    keyword = {"ANNUAL_REPORT": "年度报告", "SEMI_ANNUAL_REPORT": "半年度报告"}.get(
        slot["report_type"], "季度报告")
    title_period_ok = f"{year}年" in title_norm and keyword in title_norm
    if body_phrase:
        period_method = "BODY_PHRASE"
        period_ok = True
    elif year_in_body and title_period_ok:
        # 版式化封面的 PDF 正文常无连续短语；用官方目录标题+正文年份交叉确认，并留痕
        period_method = "TITLE_PLUS_YEAR_IN_BODY"
        period_ok = True
    else:
        period_method = "NONE"
        period_ok = False
    add("PERIOD_MATCH", period_ok,
        f"pattern={pattern}; method={period_method}; year_in_body={year_in_body}; title={title}")
    result["period_match_method"] = period_method

    form = "SUMMARY" if "摘要" in title else "FULL_TEXT"
    result["form"] = form
    add("FORM_FULL_TEXT", form == "FULL_TEXT", f"title={title}")

    critical = ("MAGIC_HEADER", "SIZE_FLOOR", "PDF_OPENABLE", "PAGE_COUNT_FLOOR",
                "ISSUER_MATCH", "PERIOD_MATCH", "FORM_FULL_TEXT")
    if all(checks[k]["result"] == "PASS" for k in critical):
        result["identity_status"] = VD_VERIFIED
    elif checks["ISSUER_MATCH"]["result"] == "FAIL" or checks["PERIOD_MATCH"]["result"] == "FAIL":
        result["identity_status"] = VD_MISMATCH
    else:
        result["identity_status"] = VD_PENDING
    return result


# ---------------------------------------------------------------- 采集器


@dataclass
class CompanyRef:
    security_id: str
    stock_code: str
    stock_name: str
    exchange: str
    listing_date: str | None = None


class Collector:
    def __init__(
        self,
        config_path: Path | str = CONFIG_PATH,
        *,
        root: Path | str = ROOT,
        transport: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        offline: bool = False,
    ):
        self.root = Path(root)
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.offline = offline
        self.http = HttpClient(self.config, transport=transport, clock=clock, sleeper=sleeper, root=self.root)
        self.ledger = Ledger(self.root / self.config["storage"]["tracked_ledger_dir"])
        self.storage_original = self.root / self.config["storage"]["local_original_root"]
        self.storage_raw = self.root / self.config["storage"]["local_raw_index_root"]
        self.cache_dir = self.root / self.config["storage"]["cache_root"]
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.events: list[dict] = []
        self._org_cache: dict[str, dict] | None = None
        self._content_index: dict[str, str] = {}
        for security_id, slot_id, record in self.ledger.iter_slots():
            doc = record.get("document") or {}
            if doc.get("sha256"):
                self._content_index.setdefault(doc["sha256"], f"{security_id}/{slot_id}")

    # -- 事件日志
    def _event(self, kind: str, **payload) -> None:
        self.events.append({"at": utc_now(), "run_id": self.run_id, "event": kind, **payload})

    def flush_events(self, path: Path | None = None) -> Path | None:
        if not self.events:
            return None
        path = Path(path) if path else (self.root / self.config["storage"]["tracked_runlog"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for ev in self.events:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.events = []
        return path

    # -- orgId 解析
    def load_org_index(self, force: bool = False) -> dict[str, dict]:
        if self._org_cache is not None and not force:
            return self._org_cache
        route = self.config["routes"]["cninfo_org_index"]
        cache_path = self.root / route["cache_path"]
        payload = None
        if cache_path.exists() and not force:
            if time.time() - cache_path.stat().st_mtime < int(route["cache_ttl_seconds"]):
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload is None:
            if self.offline:
                raise SourceFailure("ORG_INDEX_CACHE_MISSING_OFFLINE")
            payload, _ = self.http.request_json("cninfo_org_index", route["method"], route["url"])
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rows = payload.get("stockList") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            raise SourceFailure("ORG_INDEX_INVALID_SCHEMA")
        self._org_cache = {r["code"]: r for r in rows if isinstance(r, dict) and r.get("code")}
        return self._org_cache

    def resolve_org(self, company: CompanyRef) -> dict:
        idx = self.load_org_index()
        row = idx.get(company.stock_code)
        if not row:
            raise TransportFailure("ORG_ID_NOT_FOUND")
        name = row.get("zwjc") or ""
        if name and normalize_text(name) != normalize_text(company.stock_name):
            self._event("issuer_name_differs", security_id=company.security_id,
                        master=company.stock_name, cninfo=name)
        return {"org_id": row["orgId"], "cninfo_name": name}

    # -- 公告目录分页
    def fetch_index(self, company: CompanyRef, category: str, org_id: str) -> dict:
        code = company.stock_code
        ttl = int(self.config["pagination_rules"].get("index_cache_ttl_seconds", 21600))
        cached = self.ledger.get_index(code, category, ttl)
        if cached:
            self._event("index_cache_hit", security_id=company.security_id, category=category,
                        fetched_at=cached.get("fetched_at"), rows=len(cached.get("rows", [])))
            return cached
        route = self.config["routes"]["cninfo_issuer_index"]
        column = route["column_by_exchange"][company.exchange]
        page_size = int(route["page_size"])
        max_pages = int(route["max_pages"])
        params_base = {
            "tabName": route["base_params"]["tabName"],
            "searchkey": route["base_params"]["searchkey"],
            "isHLtitle": route["base_params"]["isHLtitle"],
            "column": column,
            "category": category,
            "stock": route["stock_param_format"].format(stock_code=code, org_id=org_id),
            "seDate": "2023-01-01~" + self.config["time_axis"]["knowledge_as_of"],
        }
        rows: list[dict] = []
        pages: list[dict] = []
        total: int | None = None
        seen: set[str] = set()
        raw_dir = self.storage_raw / code
        for page in range(1, max_pages + 1):
            params = dict(params_base, pageNum=str(page), pageSize=str(page_size))
            try:
                payload, call = self.http.request_json(
                    "cninfo_issuer_index", route["method"], route["url"], request_params=params, data=params)
            except DocumentUnavailable:
                pages.append({"page": page, "http_status": 404, "rows": 0, "error": "HTTP_404"})
                break
            page_rows = (payload.get("announcements") if isinstance(payload, dict) else None) or []
            if total is None and isinstance(payload, dict):
                total = payload.get("totalAnnouncement")
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{category}_p{page}.json"
            raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            new_rows = 0
            for row in page_rows:
                key = str(row.get("announcementId") or "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                rows.append(row)
                new_rows += 1
            pages.append({
                "page": page,
                "http_status": call.http_status,
                "rows": len(page_rows),
                "new_rows": new_rows,
                "total_announcement": total,
                "totalpages": payload.get("totalpages") if isinstance(payload, dict) else None,
                "has_more": payload.get("hasMore") if isinstance(payload, dict) else None,
                "response_sha256": call.response_sha256,
                "response_bytes": call.bytes,
                "raw_path": raw_path.relative_to(self.root).as_posix(),
                "request_params": params,
                "fetched_at": call.at,
                "elapsed_ms": call.elapsed_ms,
            })
            self._event("index_page", security_id=company.security_id, category=category,
                        page=page, rows=len(page_rows), total=total)
            if not page_rows:
                break
            if isinstance(total, int) and len(rows) >= total:
                break
        reconciled = isinstance(total, int) and len(rows) == total
        index = {
            "security_id": company.security_id,
            "category": category,
            "column": column,
            "org_id": org_id,
            "request_base": params_base,
            "total_announcement": total,
            "rows_fetched": len(rows),
            "pages_fetched": len(pages),
            "reconciled": reconciled,
            "status": "RECONCILED" if reconciled else ST_INDEX_INCOMPLETE,
            "pages": pages,
            "rows": [
                {
                    "announcement_id": r.get("announcementId"),
                    "title": r.get("announcementTitle"),
                    "sec_code": r.get("secCode"),
                    "sec_name": r.get("secName"),
                    "published_on": ms_to_date(r.get("announcementTime")),
                    "adjunct_url": r.get("adjunctUrl"),
                }
                for r in rows
            ],
            "fetched_at": utc_now(),
        }
        self.ledger.put_index(company.security_id, code, category, index)
        self._event("index_done", security_id=company.security_id, category=category,
                    total=total, fetched=len(rows), reconciled=reconciled, pages=len(pages))
        return index

    # -- 行 → 槽位
    @staticmethod
    def _period_of(title: str, report_type: str) -> str | None:
        norm = normalize_text(title)
        if report_type == "ANNUAL_REPORT":
            m = re.search(r"(\d{4})年年度报告", norm)
            return f"FY{m.group(1)}" if m else None
        if report_type == "SEMI_ANNUAL_REPORT":
            m = re.search(r"(\d{4})年半年度报告", norm)
            return f"{m.group(1)}H1" if m else None
        m = re.search(r"(\d{4})年第([一三])季度报告", norm)
        if not m:
            return None
        return f"{m.group(1)}Q{'1' if m.group(2) == '一' else '3'}"

    def map_rows(self, company: CompanyRef, index: dict, report_type: str) -> tuple[dict[str, list[dict]], list[dict]]:
        buckets: dict[str, list[dict]] = {}
        rejected: list[dict] = []
        for row in index.get("rows", []):
            title = row.get("title") or ""
            period = self._period_of(title, report_type)
            if not period:
                continue
            row = dict(row)
            row["revision_no"] = 1 if any(k in title for k in ("更正", "修订", "补充")) else 0
            row["is_summary"] = "摘要" in title
            sec_code = str(row.get("sec_code") or "")
            if sec_code and sec_code != company.stock_code:
                same_name = normalize_text(row.get("sec_name") or "") == normalize_text(company.stock_name)
                if same_name:
                    row["historical_code"] = True
                    self._event("historical_code_accepted", security_id=company.security_id,
                                row_code=sec_code, title=title)
                else:
                    row["rejected"] = "ISSUER_MISMATCH"
                    rejected.append(row)
                    self._event("row_rejected", security_id=company.security_id,
                                row_code=sec_code, row_name=row.get("sec_name"), title=title)
                    continue
            buckets.setdefault(period, []).append(row)
        return buckets, rejected

    @staticmethod
    def _select(rows: list[dict]) -> tuple[dict | None, dict | None]:
        full = [r for r in rows if not r["is_summary"]]
        summary = [r for r in rows if r["is_summary"]]

        def key(r):
            return (r["revision_no"], r.get("published_on") or "")

        return (max(full, key=key) if full else None, max(summary, key=key) if summary else None)

    # -- 单槽采集
    def collect_slot(self, company: CompanyRef, slot: dict, index: dict,
                     buckets: dict[str, list[dict]], *, include_optional_pdf: bool = False) -> dict:
        slot_id = slot["slot_id"]
        code = company.stock_code
        now = utc_now()
        record = self.ledger.slot(company.security_id, code, slot_id) or {
            "security_id": company.security_id,
            "slot_id": slot_id,
            "report_type": slot["report_type"],
            "period_label": slot["period_label"],
            "period_end": slot["period_end"],
            "statutory_deadline": slot["statutory_deadline"],
            "status": ST_PENDING,
            "status_reason": None,
            "attempt_count": 0,
            "source_attempts": [],
            "last_source_attempt": None,
            "last_error": None,
            "next_action": None,
            "checkpoint": {},
            "document": {},
        }
        record.setdefault("source_attempts", [])
        record.setdefault("document", {})

        # 1) 幂等跳过：本地已有同哈希原件，不发请求
        doc = record.get("document") or {}
        if record.get("status") in TERMINAL_NO_RETRY and doc.get("local_file") and doc.get("sha256"):
            local = self.root / doc["local_file"]
            if local.exists() and sha256_file(local) == doc["sha256"]:
                if "period_match_method" not in (record.get("validation") or {}):
                    # 旧版本台账缺新校验字段：用本地原件补校验，不发请求
                    slot_ctx = dict(slot, _selected_title=doc.get("title") or "")
                    record["validation"] = validate_pdf(local, slot_ctx, stock_name=company.stock_name,
                                                        stock_code=company.stock_code, config=self.config)
                # 「跳过」是动作不是状态：保留原取得状态，只记录本次未发请求
                record.update({"last_action": ST_SKIPPED,
                               "last_action_reason": "台账已有同哈希原件，本次未发出 HTTP",
                               "skip_count": int(record.get("skip_count", 0)) + 1,
                               "last_checked_at": now, "updated_at": now})
                self.ledger.put_slot(company.security_id, code, record)
                self._event("slot_skip", security_id=company.security_id, slot_id=slot_id,
                            reason="LEDGER_HASH_MATCH")
                return record

        # 2) 目录不完整：不得当作已检索
        if not index.get("reconciled"):
            record.update({
                "status": ST_INDEX_INCOMPLETE,
                "status_reason": f"累计 {index.get('rows_fetched')} != totalAnnouncement {index.get('total_announcement')}",
                "next_action": "RETRY_INDEX_WITH_CORRECTED_PARAMS",
                "last_error": "INDEX_INCOMPLETE_PAGINATION",
                "updated_at": now,
            })
            self.ledger.put_slot(company.security_id, code, record)
            return record

        full_row, summary_row = self._select(buckets.get(slot["period_label"], []))
        if full_row is None and summary_row is None:
            record.update(self._no_row_status(slot, now))
            record["index_ref"] = {"category": index["category"], "fetched_at": index["fetched_at"],
                                   "status": index["status"]}
            self.ledger.put_slot(company.security_id, code, record)
            return record
        if full_row is None:
            record.update({
                "status": ST_SUMMARY_ONLY,
                "status_reason": "目录只返回摘要，无全文",
                "next_action": "SEARCH_FULL_TEXT_ALTERNATE_SOURCE",
                "document": {"title": summary_row["title"],
                             "primary_url": f"https://static.cninfo.com.cn/{summary_row['adjunct_url']}",
                             "published_on": summary_row.get("published_on")},
                "updated_at": now,
            })
            self.ledger.put_slot(company.security_id, code, record)
            self._event("slot_summary_only", security_id=company.security_id, slot_id=slot_id)
            return record

        published = full_row.get("published_on")
        if published and published > self.config["time_axis"]["knowledge_as_of"]:
            record.update({
                "status": ST_AFTER_CUTOFF,
                "status_reason": f"披露日 {published} 晚于 knowledge_as_of",
                "next_action": "REGISTER_INCREMENTAL_CANDIDATE",
                "document": {"title": full_row["title"], "published_on": published},
                "updated_at": now,
            })
            self.ledger.put_slot(company.security_id, code, record)
            return record

        want_pdf = slot["pdf_download"] == "REQUIRED" or (slot["pdf_download"] == "OPTIONAL" and include_optional_pdf)
        if not want_pdf:
            record.update({
                "status": ST_NOT_TRIED,
                "status_reason": "本卡只登记目录链接，季度 PDF 为可选下载",
                "next_action": "ENABLE_OPTIONAL_PDF_IN_BATCH",
                "document": {"title": full_row["title"],
                             "primary_url": f"https://static.cninfo.com.cn/{full_row['adjunct_url']}",
                             "published_on": published},
                "updated_at": now,
            })
            self.ledger.put_slot(company.security_id, code, record)
            return record

        if int(record["attempt_count"]) >= int(self.config["transport"]["max_slot_attempts"]):
            record.update({"status": ST_SOURCE_FAILED, "status_reason": "超过单槽重试预算",
                           "next_action": "MANUAL_REVIEW", "updated_at": now})
            self.ledger.put_slot(company.security_id, code, record)
            return record

        url = f"https://static.cninfo.com.cn/{full_row['adjunct_url']}"
        ident = self.build_document_identity(company, slot, full_row)
        local_rel = Path(self.config["storage"]["local_original_root"]) / code / slot_id / f"{ident['document_id']}.pdf"
        local_path = self.root / local_rel
        part_path = local_path.with_suffix(".pdf.part")
        record["attempt_count"] = int(record["attempt_count"]) + 1
        record["status"] = ST_IN_PROGRESS
        record["document"] = {**ident, "title": full_row["title"], "published_on": published,
                              "primary_url": url, "local_file": local_rel.as_posix()}
        record["checkpoint"] = {"stage": "DOWNLOAD_STARTED", "url": url,
                                "part": part_path.relative_to(self.root).as_posix(),
                                "bytes_written": part_path.stat().st_size if part_path.exists() else 0,
                                "attempt": record["attempt_count"], "at": now}
        self.ledger.put_slot(company.security_id, code, record)
        self._event("download_start", security_id=company.security_id, slot_id=slot_id, url=url,
                    attempt=record["attempt_count"])

        calls: list[CallRecord] = []
        try:
            outcome, calls = self.http.download("cninfo_pdf", url, part_path, expect_pdf=True)
        except DocumentUnavailable as exc:
            record["source_attempts"].extend(c.as_dict() for c in calls)
            record.update({
                "status": ST_NOT_DISCLOSED,
                "status_reason": "目录有记录但 PDF 返回 404",
                "next_action": "REINDEX_THEN_RETRY",
                "last_error": str(exc),
                "checkpoint": {"stage": "DOWNLOAD_404", "at": utc_now()},
                "updated_at": utc_now(),
            })
            self.ledger.put_slot(company.security_id, code, record)
            return record
        except (SourceFailure, CircuitOpen) as exc:
            record["source_attempts"].extend(c.as_dict() for c in calls)
            if not record["source_attempts"]:
                record["source_attempts"].extend(c.as_dict() for c in self.http.calls[-2:])
            code_err = str(exc)
            blocked = code_err in ("HTTP_401", "HTTP_403", "HTTP_429")
            record.update({
                "status": ST_ACCESS_BLOCKED if blocked else ST_SOURCE_FAILED,
                "status_reason": f"下载失败：{code_err}",
                "last_error": code_err,
                "next_action": "MANUAL_REVIEW_ACCESS" if blocked else "WAIT_CIRCUIT_HALF_OPEN",
                "checkpoint": {"stage": "DOWNLOAD_FAILED", "at": utc_now(),
                               "part": part_path.relative_to(self.root).as_posix(),
                               "bytes_written": part_path.stat().st_size if part_path.exists() else 0},
                "updated_at": utc_now(),
            })
            self.ledger.put_slot(company.security_id, code, record)
            self._event("download_fail", security_id=company.security_id, slot_id=slot_id, error=code_err)
            return record

        record["source_attempts"].extend(c.as_dict() for c in calls)
        record["last_source_attempt"] = record["source_attempts"][-1] if record["source_attempts"] else None

        # 3) 内容级去重：同字节只入库一次，不重复计数
        digest = outcome["sha256"]
        slot_key = f"{company.security_id}/{slot_id}"
        if digest in self._content_index and self._content_index[digest] != slot_key:
            part_path.unlink(missing_ok=True)
            record["document"].update({"sha256": digest, "bytes": outcome["bytes"], "local_file": None})
            record.update({
                "status": ST_DUPLICATE,
                "status_reason": f"与 {self._content_index[digest]} 字节相同，未重复入库",
                "next_action": "NONE",
                "checkpoint": {"stage": "DONE_DUPLICATE", "at": utc_now(),
                               "deduplicated_to": self._content_index[digest]},
                "updated_at": utc_now(),
            })
            self.ledger.put_slot(company.security_id, code, record)
            self._event("slot_duplicate", security_id=company.security_id, slot_id=slot_id,
                        sha256=digest, duplicate_of=self._content_index[digest])
            return record
        self._content_index.setdefault(digest, slot_key)

        slot_ctx = dict(slot, _selected_title=full_row["title"])
        verdict = validate_pdf(part_path, slot_ctx, stock_name=company.stock_name,
                               stock_code=company.stock_code, config=self.config)
        record["validation"] = verdict

        if verdict["identity_status"] in (VD_MISMATCH, VD_UNREADABLE):
            record.update({
                "status": ST_IDENTITY_MISMATCH if verdict["identity_status"] == VD_MISMATCH else ST_SOURCE_FAILED,
                "status_reason": "文件主体/报告期与登记不符" if verdict["identity_status"] == VD_MISMATCH else "PDF 不可读或截断",
                "next_action": "MANUAL_REVIEW_IDENTITY" if verdict["identity_status"] == VD_MISMATCH else "RETRY_DOWNLOAD",
                "last_error": verdict["identity_status"],
                "checkpoint": {"stage": "REJECTED_IDENTITY" if verdict["identity_status"] == VD_MISMATCH else "DOWNLOAD_CORRUPT",
                               "at": utc_now(),
                               "bytes_written": part_path.stat().st_size if part_path.exists() else 0},
                "updated_at": utc_now(),
            })
            if verdict["identity_status"] == VD_MISMATCH:
                part_path.unlink(missing_ok=True)
            self.ledger.put_slot(company.security_id, code, record)
            self._event("pdf_rejected", security_id=company.security_id, slot_id=slot_id,
                        verdict=verdict["identity_status"], issues=verdict["issues"])
            return record

        local_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part_path, local_path)
        record["document"].update({
            "sha256": digest,
            "bytes": local_path.stat().st_size,
            "page_count": verdict.get("page_count"),
            "form": verdict.get("form"),
            "local_file": local_rel.as_posix(),
            "identity_checks": verdict["checks"],
        })
        record.update({
            "status": verdict["identity_status"],
            "status_reason": "校验通过" if verdict["identity_status"] == VD_VERIFIED else "正文抽取不足，身份待核",
            "next_action": "NONE" if verdict["identity_status"] == VD_VERIFIED else "MANUAL_IDENTITY_CHECK",
            "last_error": None,
            "checkpoint": {"stage": "DONE", "at": utc_now(), "bytes_written": local_path.stat().st_size},
            "updated_at": utc_now(),
        })
        self.ledger.put_slot(company.security_id, code, record)
        self._event("slot_done", security_id=company.security_id, slot_id=slot_id,
                    status=record["status"], sha256=digest, pages=verdict.get("page_count"))
        return record

    def _no_row_status(self, slot: dict, now: str) -> dict:
        deadline = slot.get("statutory_deadline")
        cutoff = self.config["time_axis"]["knowledge_as_of"]
        if slot.get("pre_cutoff_status") == ST_NOT_YET_DISCLOSED or (deadline and deadline > cutoff):
            return {"status": ST_NOT_YET_DISCLOSED,
                    "status_reason": f"法定披露期 {deadline} 晚于截止日 {cutoff}",
                    "next_action": "WAIT_NEXT_CYCLE", "last_error": None, "updated_at": now}
        return {"status": ST_NOT_TRIED,
                "status_reason": "目录已完整检索但无该期全文；listing_date 未知，不得判不适用或未披露",
                "next_action": "RESOLVE_LISTING_DATE", "last_error": None, "updated_at": now,
                "reason_code": "LISTING_DATE_UNKNOWN_EMPTY_INDEX"}

    def build_document_identity(self, company: CompanyRef, slot: dict, row: dict) -> dict:
        ident = self.config["identity"]
        key = ident["key_template"].format(
            security_id=company.security_id,
            issuer_scope=ident["issuer_scope_default"],
            document_type=slot["report_type"],
            period_key=slot["period_label"],
            revision_no=row.get("revision_no", 0),
        )
        document_id = "DOC-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16].upper()
        return {"document_id": document_id, "identity_key": key, "revision_no": row.get("revision_no", 0),
                "source_type": "CNINFO_OFFICIAL_PDF"}

    # -- 公司级
    def collect_company(self, company: CompanyRef, slot_ids: list[str] | None = None,
                        *, include_optional_pdf: bool = False) -> dict:
        exchange, _ = parse_security_id(company.security_id)
        if exchange != company.exchange:
            raise ValueError("CompanyRef.exchange 与 security_id 不一致")
        slots = [s for s in self.config["slots"] if slot_ids is None or s["slot_id"] in slot_ids]
        try:
            org = self.resolve_org(company)
        except (SourceFailure, CircuitOpen, TransportFailure) as exc:
            return {"security_id": company.security_id, "org_id": None,
                    "slots": self._fail_all(company, slots, exc)}
        results: list[dict] = []
        by_type: dict[str, list[dict]] = {}
        for s in slots:
            by_type.setdefault(s["report_type"], []).append(s)
        for report_type, group in by_type.items():
            if report_type == "QUARTERLY_REPORT":
                for sub in group:
                    cat = self.config["categories"][
                        "QUARTERLY_REPORT_Q1" if sub["period_label"].endswith("Q1") else "QUARTERLY_REPORT_Q3"]
                    try:
                        index = self.fetch_index(company, cat, org["org_id"])
                    except (SourceFailure, CircuitOpen, TransportFailure) as exc:
                        results.extend(self._fail_all(company, [sub], exc))
                        continue
                    buckets, _ = self.map_rows(company, index, "QUARTERLY_REPORT")
                    results.append(self.collect_slot(company, sub, index, buckets,
                                                     include_optional_pdf=include_optional_pdf))
                continue
            category = self.config["categories"][report_type]
            try:
                index = self.fetch_index(company, category, org["org_id"])
            except (SourceFailure, CircuitOpen, TransportFailure) as exc:
                results.extend(self._fail_all(company, group, exc))
                continue
            buckets, rejected = self.map_rows(company, index, report_type)
            if rejected:
                index["rejected_rows"] = rejected
                self.ledger.put_index(company.security_id, company.stock_code, category, index)
            for sub in group:
                results.append(self.collect_slot(company, sub, index, buckets,
                                                 include_optional_pdf=include_optional_pdf))
        return {"security_id": company.security_id, "org_id": org["org_id"], "slots": results}

    def _fail_all(self, company: CompanyRef, slots: list[dict], exc: Exception) -> list[dict]:
        code = str(exc)
        blocked = code in ("HTTP_401", "HTTP_403", "HTTP_429")
        out = []
        for slot in slots:
            record = self.ledger.slot(company.security_id, company.stock_code, slot["slot_id"]) or {
                "security_id": company.security_id, "slot_id": slot["slot_id"],
                "report_type": slot["report_type"], "period_label": slot["period_label"],
                "period_end": slot["period_end"], "statutory_deadline": slot["statutory_deadline"],
                "attempt_count": 0, "source_attempts": [], "document": {}, "checkpoint": {},
            }
            record.setdefault("source_attempts", [])
            record.setdefault("document", {})
            record.update({
                "status": ST_ACCESS_BLOCKED if blocked else ST_NOT_TRIED,
                "status_reason": f"目录检索未完成：{code}；未尝试不等于缺件",
                "last_error": code,
                "next_action": "MANUAL_REVIEW_ACCESS" if blocked else "WAIT_CIRCUIT_HALF_OPEN",
                "updated_at": utc_now(),
            })
            self.ledger.put_slot(company.security_id, company.stock_code, record)
            out.append(record)
        return out

    # -- 批量
    def run(self, companies: list[CompanyRef], slot_ids: list[str] | None = None,
            *, include_optional_pdf: bool = False) -> dict:
        self._event("run_start", companies=len(companies), slots=slot_ids or "ALL",
                    include_optional_pdf=include_optional_pdf)
        results = []
        try:
            for company in companies:
                results.append(self.collect_company(company, slot_ids,
                                                    include_optional_pdf=include_optional_pdf))
        except KeyboardInterrupt:
            self._event("run_interrupted", completed=len(results))
            self.flush_events()
            raise SystemExit(130)
        finally:
            self.flush_events()
        summary = self.summarize(results)
        self._event("run_end", **summary)
        self.flush_events()
        return {"run_id": self.run_id, "companies": results, "summary": summary,
                "circuit": self.http.circuit_snapshot(), "http_calls": len(self.http.calls)}

    @staticmethod
    def summarize(results: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for company in results:
            for slot in company["slots"]:
                counts[slot["status"]] = counts.get(slot["status"], 0) + 1
        obtained = sum(counts.get(s, 0) for s in OBTAINED_STATUSES)
        return {"slot_total": sum(counts.values()), "status_counts": counts, "obtained": obtained}


def load_companies(path: Path | str, security_ids: list[str] | None = None) -> list[CompanyRef]:
    import csv

    refs = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if security_ids and row["security_id"] not in security_ids:
                continue
            listing = row.get("listing_date") or ""
            refs.append(CompanyRef(
                security_id=row["security_id"],
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                exchange=row["exchange"],
                listing_date=None if listing in ("", "UNKNOWN") else listing,
            ))
    return refs


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="P05 采集器：分页 / 断点 / 校验 / 限速 / 熔断")
    parser.add_argument("--security", action="append", default=[], help="如 SH:688218，可重复")
    parser.add_argument("--slot", action="append", default=[], help="如 annual_2025，可重复；缺省为全部槽")
    parser.add_argument("--include-optional-pdf", action="store_true", help="季报 PDF 也下载")
    parser.add_argument("--companies", default=str(ROOT / "data/company_master.csv"))
    parser.add_argument("--offline", action="store_true", help="只用本地缓存，不发新请求")
    parser.add_argument("--summary-out", default="")
    args = parser.parse_args(argv)

    companies = load_companies(args.companies, args.security or None)
    if args.security:
        missing = set(args.security) - {c.security_id for c in companies}
        if missing:
            print(json.dumps({"error": "security_not_in_master", "missing": sorted(missing)}, ensure_ascii=False))
            return 2
    collector = Collector(offline=args.offline)
    result = collector.run(companies, args.slot or None, include_optional_pdf=args.include_optional_pdf)
    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
