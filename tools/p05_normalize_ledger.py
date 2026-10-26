"""一次性台账归一化：把历史记录里的「跳过」从状态改回动作，并统一路径分隔符。

背景：早期实现把 SKIPPED_ALREADY_HAVE 写成 status，会覆盖真实取得状态。
改为 status 保留 COLLECTED_*、另记 last_action=SKIPPED_ALREADY_HAVE 后，
需要对已产生的台账做一次幂等迁移。可重复运行。
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "runs/issues/P05/checkpoint"
BACKSLASH = chr(92)


def main() -> int:
    changed_files = 0
    for path in sorted(LEDGER.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for _, rec in data.get("slots", {}).items():
            doc = rec.get("document") or {}
            val = rec.get("validation") or {}
            if rec.get("status") == "SKIPPED_ALREADY_HAVE":
                rec["status"] = val.get("identity_status", "COLLECTED_IDENTITY_VERIFIED")
                rec["last_action"] = "SKIPPED_ALREADY_HAVE"
                rec["last_action_reason"] = "台账已有同哈希原件，本次未发出 HTTP"
                rec["skip_count"] = int(rec.get("skip_count", 0)) + 1
                rec["status_reason"] = ("校验通过" if rec["status"] == "COLLECTED_IDENTITY_VERIFIED"
                                        else "正文抽取不足，身份待核")
                changed = True
            for key in ("local_file",):
                if isinstance(doc.get(key), str) and BACKSLASH in doc[key]:
                    doc[key] = doc[key].replace(BACKSLASH, "/")
                    changed = True
            cp = rec.get("checkpoint") or {}
            if isinstance(cp.get("part"), str) and BACKSLASH in cp["part"]:
                cp["part"] = cp["part"].replace(BACKSLASH, "/")
                changed = True
        for _, idx in data.get("indexes", {}).items():
            for page in idx.get("pages", []):
                if isinstance(page.get("raw_path"), str) and BACKSLASH in page["raw_path"]:
                    page["raw_path"] = page["raw_path"].replace(BACKSLASH, "/")
                    changed = True
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            changed_files += 1
            print(f"normalized {path.name}")
    print(f"files changed: {changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
