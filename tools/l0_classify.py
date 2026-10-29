#!/usr/bin/env python3
"""Apply the proposed exhaustive S02 L0 addendum to a 12-metric summary."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/issues/S02/remediation_20261029/l0"
SUMMARY = ROOT / "runs/issues/S02/company_metric_summary.csv"
PATCH = OUT / "l0_rules_patch.json"
S01_RULES = ROOT / "runs/issues/S01/screen_rules_v2.json"
COUNT_COLUMNS = {
    "OK": "ok",
    "PROVISIONAL": "provisional",
    "HOLD": "hold",
    "MISSING": "missing",
    "NOT_COMPARABLE": "not_comparable",
    "UNDEFINED_BASE": "undefined_base",
    "NOT_APPLICABLE": "not_applicable",
    "EXCLUDED_SCOPE": "excluded_scope",
    "VERSION_MISMATCH": "version_mismatch",
}
EXPECTED_COMPANIES = 1054
EXPECTED_METRICS = 12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _validate_condition(node: object, statuses: set[str], *, allow_otherwise: bool = False) -> None:
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError(f"each condition must be a one-key object: {node!r}")
    key, value = next(iter(node.items()))
    if key in ("all", "any"):
        if not isinstance(value, list) or not value:
            raise ValueError(f"{key} requires a non-empty list")
        for child in value:
            _validate_condition(child, statuses, allow_otherwise=False)
    elif key == "count":
        if not isinstance(value, dict) or set(value) != {"status", "op", "value"}:
            raise ValueError("count condition requires status, op, and value")
        if value["status"] not in statuses:
            raise ValueError(f"unknown status in count condition: {value['status']!r}")
        if value["op"] not in {"eq", "gte"}:
            raise ValueError(f"unsupported count operator: {value['op']!r}")
        if type(value["value"]) is not int or value["value"] < 0:
            raise ValueError("count condition values must be non-negative integers")
    elif key in {"active_statuses_exactly", "active_statuses_subset_of"}:
        if not isinstance(value, list) or not value or len(value) != len(set(value)):
            raise ValueError(f"{key} requires a non-empty list of unique statuses")
        if not set(value) <= statuses:
            raise ValueError(f"unknown status in {key}: {sorted(set(value) - statuses)}")
    elif key == "otherwise":
        if value is not True or not allow_otherwise:
            raise ValueError("otherwise:true is only valid as a top-level final rule condition")
    else:
        raise ValueError(f"unsupported condition operator: {key!r}")


def _load_rule_table() -> tuple[tuple[str, ...], list[dict]]:
    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    statuses = tuple(patch["classification_input"]["allowed_metric_statuses"])
    if set(statuses) != set(COUNT_COLUMNS) or len(statuses) != len(COUNT_COLUMNS):
        raise ValueError("patch status enum and summary count columns differ")
    if patch["classification_input"]["metric_count"] != EXPECTED_METRICS:
        raise ValueError("patch metric_count differs from the 12-metric S02 summary")
    rules = patch["priority_rules"]
    priorities = [rule.get("priority") for rule in rules]
    if priorities != list(range(1, len(rules) + 1)):
        raise ValueError("patch priorities must be unique, contiguous, and already ordered")
    if not rules:
        raise ValueError("patch has no priority rules")
    for index, rule in enumerate(rules):
        for key in ("output", "condition", "l1_route", "l2_route"):
            if key not in rule:
                raise ValueError(f"rule {rule.get('priority')} is missing {key}")
        is_last = index == len(rules) - 1
        _validate_condition(rule["condition"], set(statuses), allow_otherwise=is_last)
        if "otherwise" in rule["condition"] and not is_last:
            raise ValueError("otherwise rule must be last")
    if len({rule["output"] for rule in rules}) != len(rules):
        raise ValueError("rule outputs must be unique")
    return statuses, rules


STATUSES, RULE_TABLE = _load_rule_table()


def _condition_matches(condition: dict, counts: dict[str, int]) -> bool:
    key, value = next(iter(condition.items()))
    if key == "all":
        return all(_condition_matches(child, counts) for child in value)
    if key == "any":
        return any(_condition_matches(child, counts) for child in value)
    if key == "count":
        actual = counts[value["status"]]
        return actual == value["value"] if value["op"] == "eq" else actual >= value["value"]
    active = {status for status, count in counts.items() if count}
    if key == "active_statuses_exactly":
        return active == set(value)
    if key == "active_statuses_subset_of":
        return active <= set(value)
    if key == "otherwise":
        return True
    raise ValueError(f"unsupported condition operator: {key!r}")


def _validate_counts(counts: dict[str, int], statuses: tuple[str, ...]) -> None:
    if set(counts) != set(statuses):
        raise ValueError(f"status keys differ from the frozen enum: {sorted(set(counts) ^ set(statuses))}")
    if any(type(counts[status]) is not int or counts[status] < 0 for status in statuses):
        raise ValueError("status counts must be non-negative integers")
    if sum(counts.values()) != EXPECTED_METRICS:
        raise ValueError(f"expected {EXPECTED_METRICS} metrics, got {sum(counts.values())}")


def _classify_with_rules(counts: dict[str, int], rules: list[dict]) -> tuple[str, str, str]:
    """Interpret the JSON rule conditions; return (L0, L1 route, L2 route)."""
    _validate_counts(counts, STATUSES)
    matches = []
    for rule in rules:
        condition = rule["condition"]
        if "otherwise" in condition:
            matched = not matches
        else:
            matched = _condition_matches(condition, counts)
        if matched:
            matches.append(rule)
    if len(matches) != 1:
        raise ValueError(f"status vector must match exactly one L0 rule, matched {len(matches)}")
    rule = matches[0]
    return rule["output"], rule["l1_route"], rule["l2_route"]


def classify(counts: dict[str, int]) -> tuple[str, str, str]:
    """Public/importable classifier using the structured JSON patch as its source."""
    return _classify_with_rules(counts, RULE_TABLE)


def parse_count(value: str, column: str, row_num: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_num}: {column} is not an integer: {value!r}") from exc
    if str(parsed) != str(value).strip() or parsed < 0:
        raise ValueError(f"row {row_num}: {column} must be a canonical non-negative integer: {value!r}")
    return parsed


def weak_compositions(total: int, bins: int):
    """Yield every non-negative count vector summing to total."""
    if bins == 1:
        yield (total,)
        return
    for head in range(total + 1):
        for tail in weak_compositions(total - head, bins - 1):
            yield (head,) + tail


def exhaustive_check() -> dict:
    routes = Counter()
    vectors = 0
    for vector in weak_compositions(EXPECTED_METRICS, len(STATUSES)):
        counts = dict(zip(STATUSES, vector))
        route, _, _ = classify(counts)
        routes[route] += 1
        vectors += 1
    expected_vectors = comb(EXPECTED_METRICS + len(STATUSES) - 1, len(STATUSES) - 1)
    expected_outputs = {rule["output"] for rule in RULE_TABLE}
    if vectors != expected_vectors or sum(routes.values()) != expected_vectors:
        raise AssertionError(f"enumeration coverage mismatch: {vectors} vectors, {expected_vectors} expected")
    if set(routes) != expected_outputs:
        raise AssertionError(f"unreachable or undeclared branch: {sorted(set(routes) ^ expected_outputs)}")

    invalid_cases = [
        ({**{status: 0 for status in STATUSES}, "OK": 13}, "wrong total"),
        ({**{status: 0 for status in STATUSES}, "BOGUS": 12}, "unknown status"),
        ({**{status: 0 for status in STATUSES}, "OK": -1, "MISSING": 13}, "negative count"),
    ]
    for counts, label in invalid_cases:
        try:
            classify(counts)
        except ValueError:
            continue
        raise AssertionError(f"invalid vector was accepted: {label}")
    return {
        "legal_count_vectors": vectors,
        "branch_count_vectors": dict(sorted(routes.items())),
        "invalid_input_cases_rejected": len(invalid_cases),
        "all_declared_branches_reachable": True,
        "one_rule_per_legal_vector": True,
        "conditions_source": "l0_rules_patch.json priority_rules[].condition",
    }


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def output_directory(summary: Path, explicit_out: str | None) -> Path:
    if explicit_out:
        result = Path(explicit_out).expanduser().resolve()
    elif summary.resolve() == SUMMARY.resolve():
        result = OUT.resolve()
    else:
        result = OUT / "rechecks" / f"{summary.stem}_{sha256(summary)[:12]}"
    if summary.resolve() != SUMMARY.resolve() and result == OUT.resolve():
        raise ValueError("a custom --summary cannot write into the baseline output directory; choose a separate --out")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", help="company_metric_summary.csv to classify; defaults to the S02 baseline")
    parser.add_argument("--out", help="separate output directory; custom summaries get a content-addressed recheck directory by default")
    args = parser.parse_args(argv)

    summary = Path(args.summary).expanduser().resolve() if args.summary else SUMMARY.resolve()
    if not summary.is_file():
        raise FileNotFoundError(f"summary file not found: {summary}")
    out_dir = output_directory(summary, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    actual_rules_sha = sha256(S01_RULES)
    accepted_hash = "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85"
    allowed_bytes = {accepted_hash, *patch.get("base_rules_line_ending_equivalents", [])}
    if patch["base_rules_sha256"] != accepted_hash or actual_rules_sha not in allowed_bytes:
        raise ValueError("L0 patch base hash does not match the S01 frozen v2 acceptance record")
    if set(STATUSES) != set(patch["classification_input"]["allowed_metric_statuses"]):
        raise ValueError("loaded classifier enum differs from the current machine-readable patch")

    with summary.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != EXPECTED_COMPANIES:
        raise ValueError(f"expected {EXPECTED_COMPANIES} companies, got {len(rows)}")
    security_ids = [row.get("security_id", "") for row in rows]
    if not all(security_ids) or len(set(security_ids)) != EXPECTED_COMPANIES:
        raise ValueError("security_id values must be non-empty and unique")

    results = []
    branch_counts = Counter()
    status_sums = Counter()
    for row_num, row in enumerate(rows, 2):
        counts = {
            status: parse_count(row.get(column, ""), column, row_num)
            for status, column in COUNT_COLUMNS.items()
        }
        if parse_count(row.get("metrics_with_status", ""), "metrics_with_status", row_num) != EXPECTED_METRICS:
            raise ValueError(f"row {row_num}: metrics_with_status is not {EXPECTED_METRICS}")
        route, l1_route, l2_route = classify(counts)
        branch_counts[route] += 1
        status_sums.update(counts)
        results.append({
            "security_id": row["security_id"],
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "period_key": row["period_key"],
            "prior_l0_evaluability": row["l0_evaluability"],
            "l0_evaluability_v3_addendum": route,
            "l1_route": l1_route,
            "l2_route": l2_route,
            **{column: counts[status] for status, column in COUNT_COLUMNS.items()},
            "metrics_with_status": EXPECTED_METRICS,
        })

    if sum(branch_counts.values()) != EXPECTED_COMPANIES:
        raise AssertionError("classification did not route every company exactly once")

    output_name = "l0_reclassification_baseline.csv" if out_dir.resolve() == OUT.resolve() else "l0_reclassification.csv"
    output_csv = out_dir / output_name
    with output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)

    exhaustive = exhaustive_check()
    report = {
        "status": "SELF_CHECK_PASS",
        "review_nature": "SELF_CHECK",
        "rules_version": patch["rules_version"],
        "base_rules_version": patch["base_rules_version"],
        "base_rules_sha256": patch["base_rules_sha256"],
        "observed_base_rules_sha256": actual_rules_sha,
        "input": display_path(summary),
        "input_sha256": sha256(summary),
        "input_companies": len(rows),
        "input_cells_per_company": EXPECTED_METRICS,
        "input_status_cell_totals": dict(sorted(status_sums.items())),
        "reclassified_company_counts": dict(sorted(branch_counts.items())),
        "historical_baseline_counts": dict(sorted(Counter(row["l0_evaluability"] for row in rows).items())),
        "exhaustive_branch_check": exhaustive,
        "outputs": [display_path(output_csv), display_path(out_dir / "self_check.json")],
        "limits": [
            "This is a proposed technical rule addendum and a self-check, not independent acceptance.",
            "It does not edit the frozen S01 v2 rules, formulas, thresholds, S02 historical files, or source rows.",
            "The current baseline source is pre-correction; post-remediation counts must be recalculated from the new S02 output.",
            "L0 classification is not L1 signal evaluation, L2 shortlist qualification, or authorization to start S03.",
        ],
    }
    (out_dir / "self_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "summary": display_path(summary),
        "output_dir": display_path(out_dir),
        "companies": len(rows),
        "branches": dict(sorted(branch_counts.items())),
        "exhaustive_vectors": exhaustive["legal_count_vectors"],
        "all_declared_branches_reachable": exhaustive["all_declared_branches_reachable"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
