import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "runs/issues/S03/rerun_20261106"
GUARDS = {"SH:603448", "SH:688836", "SZ:301348", "SZ:301699"}
sys.path.insert(0, str(ROOT / "runs/issues/S03"))
import l1_screen as screen


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["company_id"]: r for r in csv.DictReader(fh)}


old = rows(ROOT / "runs/issues/S03/l1_screen_results.csv")
new = rows(OUT / "l1_screen_results.csv")
assert len(new) == 1054 and set(old) == set(new)
assert all(old[k] == new[k] for k in new.keys() - GUARDS), "non-guard companies changed"
assert all(
    new[k]["l1_subtag"] == "WATCH_AFTER_CUTOFF"
    and new[k]["s04_review_priority"] == "WATCH_AFTER_CUTOFF"
    and not any(
        new[k][x]
        for x in (
            "sg_hit_clean_list", "sg_hit_provisional_list", "sg_hit_lowbase_list",
            "sg_hit_all_list", "rh_hit_list", "sg_blocked_would_fire", "rh_blocked_would_fire",
        )
    )
    and (new[k]["clean_ok_dims_count"], new[k]["total_potential_dims_count"], new[k]["hold_dims_count"])
    == ("0", "0", "0")
    for k in GUARDS
)

with tempfile.TemporaryDirectory(dir=OUT) as temp:
    temp = Path(temp)
    assert screen.main(out_dir=temp / "missing", contract_path=temp / "absent.json") == 2
    bad = json.loads(
        (ROOT / "runs/issues/S02/acceptance_20261106/s03_input_contract.json").read_text(encoding="utf-8")
    )
    bad["metrics"]["sha256"] = "0" * 64
    bad_path = temp / "tampered.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    assert screen.main(out_dir=temp / "tampered", contract_path=bad_path) == 2
    assert not (temp / "missing").exists() and not (temp / "tampered").exists()

print(json.dumps({
    "all_companies": len(new), "guarded": len(GUARDS), "non_guard_rowwise_unchanged": 1050,
    "missing_contract_rejected": True, "tampered_hash_rejected": True,
}, indent=2))
