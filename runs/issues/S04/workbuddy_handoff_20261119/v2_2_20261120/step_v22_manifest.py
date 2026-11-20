# -*- coding: utf-8 -*-
"""生成 V2.2 清单。必须在「构建 → 自检 → 数字校验」全部完成后运行，
否则自检会重写 generated_at 导致哈希漂移。
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))

INPUTS = {
    "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz": "",
    "runs/issues/S01/screen_rules_v3.json": "",
    "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json": "",
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    files = []
    for name in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, name)
        if not os.path.isfile(p) or name == "manifest.json":
            continue
        files.append({"path": name, "bytes": os.path.getsize(p), "sha256": sha(p)})

    fps = {k: sha(os.path.join(REPO, k.replace("/", os.sep))) for k in INPUTS}

    m = {
        "artifact": "S05_V22_MANIFEST",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "plan_version": "20261026_collection_first_v2",
        "ruling": "runs/issues/S04/codex_ruling_s05_v21_20261120.md",
        "prior_ruling": "runs/issues/S04/codex_ruling_s05_v2_20261120.md",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "release_S05": False,
        "branch_refs": {
            "online_main_ref": "a308fab19c17ea0184df0d730f2a5723760f2ef4",
            "local_main_ref": "15dd324c2dcebc7a9e64192c42f69fe704abe652",
        },
        "files": files,
        "inputs_fingerprints": fps,
        "hash_note": "files[] 的哈希在最后一次自检与数字校验之后计算；顺序必须是 构建→自检→数字校验→哈希。",
        "notes": [
            "V1、V2、V2.1 均保留为被裁决对象，不删不改。",
            "三格来源不准入按「公司+字段+期间+文档 SHA-256」登记，冻结底表未覆盖。",
            "Q10 与 RH03 共用 ca_source_admissible()；采用金额须绑定期间 + 合并表 + 合同资产行 + 期末列。",
            "RH02 = 118 可判 / 31 项目制不适用 / 129 待核；RH03 = 133/126/18/1。",
            "行级 8,005/76/534/8/15 = 8,638；转移 16 行只落三家。",
            "自检 39/39；汇报数字校验 73/73；release_S05 仍 false。",
        ],
    }
    with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    print(json.dumps({"files": len(files), "inputs": len(fps)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
