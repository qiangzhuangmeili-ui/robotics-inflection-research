# S02 L0 remediation

This is an additive, proposed rule patch for the gap recorded in S02. It does not change the frozen S01 v2 formulas, thresholds, signal definitions, source data, or historical deliverables. The full machine-readable decision table is in `l0_rules_patch.json`.

The previous S02 implementation had three effective routes: any `OK` became `EVALUABLE`, any `PROVISIONAL` with no `OK` became `W5_PROVISIONAL_ONLY`, and the remainder fell into an undefined mixed bucket except for all-HOLD, all-MISSING, or all-NOT_COMPARABLE. This patch gives every valid 12-metric status vector exactly one route. The 377 W5 and 17 mixed companies reported in S02 are baseline diagnostics only; recalculating after upstream fixes may change both counts.

`W5_PROVISIONAL_ONLY` is a metric-layer observation route: there is no clean `OK` metric and at least one provisional metric. Other unavailable statuses may coexist. No `OK` across all 12 metrics means the current run cannot satisfy the clean L2 candidate gate, but it does not mean there is no signal. A provisional signal may enter L1 observation under the frozen rule with its provisional mark. No provisional trigger leaves the company on W5; it does not become `NO_SIGNAL` or an automatic signal-based rejection. L0 never adds a candidate. The other no-OK/no-provisional routes stay held for data, history, scope, version, or mixed-status review. `EVALUABLE` only allows status-aware signal evaluation; it is never a candidate decision by itself.

Run the baseline from the repository root with the bundled Python runtime or a normal Python 3 installation:

```powershell
python tools/l0_classify.py
```

The priority conditions in `l0_rules_patch.json` are the sole source of branch semantics. The imported `classify(counts)` function and the exhaustive check both interpret those JSON conditions; the check requires exactly one match per legal vector and verifies that every declared branch is reachable.

To classify a corrected S02 summary without replacing the baseline outputs, pass the corrected input and a separate output directory:

```powershell
python tools/l0_classify.py --summary runs/issues/S02/rework/company_metric_summary.csv --out runs/issues/S02/remediation_20261029/l0/post_fix
```

If `--summary` is custom and `--out` is omitted, the script picks a content-addressed subdirectory under `l0/rechecks/`. It refuses to write a custom summary into the baseline output directory. The script validates 1,054-company coverage and exhaustively evaluates all 125,970 non-negative count vectors of 12 cells over the nine allowed statuses. It fails closed on unknown statuses, malformed counts, duplicate companies, or incomplete rows. It does not edit the source summary or frozen S01 rules.

This implementation and verification are `SELF_CHECK`; they are not independent business acceptance or permission to start S03. The 53-company extraction/measurement findings remain upstream work and must be resolved separately.
