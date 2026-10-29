# SELF_CHECK / INTEGRATION_REVIEW

## Scope and result

Reviewed and corrected the S02 calculation entry point for the v1 baseline, the registered S00 v2 repair input, and the legacy rebuild.py monkeypatch call. This is a SELF_CHECK/INTEGRATION_REVIEW; it is not an independent source-PDF audit or S02 release. S03 was not started.

Only tools/s02_calculate.py was changed. Test scripts and generated run outputs are under this integration directory. Existing runs/issues/S02/ and runs/issues/S02/remediation_20261029/s02* deliverables were not written by these tests.

## Integration changes

- Resolve the effective input from --normalized or the already configured s01.NORMALIZED, and use that same resolved path and SHA for loading, v1/v2 detection, P05, and the manifest.
- P02 continues to validate the three frozen S01 baseline fingerprints. P05 binds loaded CSV bytes to a rules-registered CSV, a registered gzip (both compressed SHA and decompressed payload SHA), the PROJECT_STATE.current_valid_versions.S00_data.v2_repair payload, or an explicit --normalized-sha256. Same-content CSV copies are recognized by payload SHA. Unknown or mismatched inputs stop before calculation.
- A .csv.gz CLI input is materialized only beneath the explicit --out-dir cache. The manifest separates source path/compressed-byte SHA from loaded CSV path/payload SHA. A copy of the registered v2 CSV and a PROJECT_STATE-identified copy both trigger automatic L0 classification.
- S01 rules are accepted only when their science sections match the frozen rules and the base byte SHA is one of the recorded CRLF/LF equivalents. The v2 input metadata may vary; formula, signal, and threshold content may not.
- A recognized v2 input applies the JSON L0 addendum during the S02 company-summary build. The patch version/path/SHA is checked against the repair S02 manifest. V1 keeps its historical labels; P06 is NOT_APPLICABLE with required=false for v1, and requires required=true plus applied=true for v2.
- The manifest records the actual rules path, normalized source and loaded-input paths/SHAs, applied addendum path/version/SHA, and execution_sources: calculator, formula engine, classifier, applied L0 rules, A03 source and registered parser SHA, and reextract-plan SHA. It explicitly records that A03 extraction did not execute in this run.
- main() defaults to an empty argv for wrapper callers; the command-line entry explicitly passes sys.argv[1:]. Per-run checks and findings are reset.

## Verification

Run from the repository root:

    $env:PYTHONDONTWRITEBYTECODE = '1'
    & 'C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B runs/issues/S02/recheck_20261029/integration/test_s02_integration.py

Result: 11 tests passed. Coverage includes default v1, v2 CLI, the old wrapper call with inherited sys.argv, accepted S01 line-ending hashes and changed-threshold rejection, unknown input and wrong SHA blocking, tampered CSV and tampered L0 patch blocking, registered-payload CSV-copy recognition, PROJECT_STATE payload-copy recognition, direct gzip CLI materialization and source/loaded hash recording, v2 W9 routing, and a v2 loader fault injection that confirms P06 blocks an unapplied addendum.

The v2 outputs in v2_cli/ and old_wrapper/ report 664 EVALUABLE, 387 W5, and 3 W9; neither emits MIXED_NOT_DEFINED_BY_RULE. The v1 output retains 660 EVALUABLE, 377 W5, and 17 historical MIXED labels. The v2 CLI output's all_pool_metrics.csv and company_metric_summary.csv are byte-identical to their frozen canonical counterparts. The execution-source record reports that the current A03 source SHA matches the parser SHA registered in the reextract plan.

Python source compilation passed. git -c core.whitespace=cr-at-eol diff --check -- tools/s02_calculate.py passed, honoring the repository's * -text line-ending rule.

## Limits

The rerun confirms deterministic calculation and integration behavior only. It does not independently validate the 19 PDF page expectations, the 360 source PDF hashes, or the upstream parser implementation. No external acceptance or S03 release is asserted.
