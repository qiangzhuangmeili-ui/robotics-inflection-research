# Recovery18 v3 recalculation (prepared, not run)

This directory contains an isolated runner for the targeted S00 + S02 v3
recalculation. It is labelled `SELF_CHECK`; it does not release S03 or claim an
independent audit of source PDF pages. The script has not been run because the
three correction packages are not complete yet.

## Inputs and bounded scope

The runner starts from all 360 accepted v2 extraction JSONs in
`runs/issues/S02/remediation_20261029/extracted/`, in the order recorded by the
frozen `reextract_plan.json`. It then replaces matching `(security_id, slot_id)`
records with JSONs found recursively under:

- `recovery18_20261029/xcheck11/corrected_results/`
- `recovery18_20261029/scope5/corrected_results/`
- `recovery18_20261029/ocr2/corrected_results/`

Before calculation, it derives the unresolved 21-company set from the frozen
v2 `coverage_resolution.csv` and removes the three
`NO_CURRENT_PDF_LEGACY_ONLY` exclusions. It then applies the confirmed source
team split, which crosses the old resolution labels:

- `scope5`: BJ:920146, BJ:920198, SH:600444, SZ:301348, SZ:002594
- `ocr2`: SH:601390, SZ:002083
- `xcheck11`: the exact remainder of the unresolved 21 after the three
  exclusions and the seven IDs above

It requires the correction directories to cover exactly those 18 companies,
with group counts 11/5/2 and no overlap. The excluded IDs are SH:603448,
SH:688836, and SZ:301699. Every correction must match a frozen
`(security_id, slot_id, document_id)` task; its registered PDF bytes are hashed
against the collection-plan SHA before ingestion.

## Calculation and controls

The script installs temporary in-memory S00 loaders and calls the existing
`tools/s00_normalize.py`. It then creates a deterministic gzip and a v3 input
fingerprint, and invokes the current S02 CLI API with explicit `--normalized`,
`--rules`, and `--out-dir` arguments. S02 P01 locks the formula and signal
threshold definitions to S01 v2; P05 binds the generated gzip; P06 must apply
the frozen L0 addendum. The runner does not copy formulas or thresholds, and
it does not call A03 extraction.

The v3 runner also loads the parent-provided
`recovery18_20261029/comparability_holds.json` and verifies its registered PDF
SHA. The independent `comparability_adapter.py` tags every normalized row for
the specified company/period, preserves the reported amount and consolidated
scope, and changes only `DERIVED_CUMULATIVE_DIFF` single-quarter rows to
`DERIVED_HOLD_UPSTREAM` with a page-linked scope trace. Directly reported Q3
single-quarter values remain intact. Before S02, the adapter wraps the existing
`S.s01._inputs(recs)`: it keeps every original non-OK result and changes only an
originally-OK input set containing the scope tag to `HOLD` with `Q01`. The
adapter hash, hold-spec hash, tagged-row count, derived-SQ hold count, and S02
input-gate counts are written into the manifests. Any later S03 replay must use
the same guard and scope-hold specification. The production
`tools/s02_calculate.py` script alone does not reproduce this P04 scope guard;
the integration runner must install the registered adapter around its
`S.main()` calculation. Any separate S02 replay or recomputation must install
the same adapter too.

After the normalized CSV is tagged, the runner refreshes its row count, byte
length, and SHA256 in the S00 manifest's `outputs.financial_normalized.csv`
record. It compares every parsed row for all 1,036 non-target companies across
the normalized CSV, all-pool metrics, and company summary; non-target findings
in `metric_qc_findings.csv` must also remain unchanged. The complete frozen S01
rule object is checked at every non-input-metadata top-level key before S02.

The run compares full CSV rows against the frozen v2 outputs. Any normalized,
metric, or company-summary row changes outside the 18 correction-company IDs
stop the run. `coverage_resolution_v2_v3.csv` gives a per-company comparison of
status counts and usable-cell counts; `normalized_delta_v2_v3.csv`,
`metric_delta_v2_v3.csv`, and `company_summary_delta_v2_v3.csv` retain changed
columns and complete old/new rows. The manifests record the 360 base JSON
hashes, every correction JSON hash, registered source-PDF path/SHA, actual
PDF-byte SHA, S00/S02/formula/L0 source hashes, input and output hashes, and
explicitly state `external_source_evidence_review=NOT_PERFORMED` and
`next_stage_release=S03_LOCKED`.

## Execution

Do not run before the parent confirms that all three correction packages are
ready. The default output path must not already exist; the runner refuses to
overwrite output. Run from the repository root after that confirmation:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B `
  runs/issues/S02/recovery18_20261029/integration/rebuild_v3.py --execute
```

To preserve a prior attempt, select a new child directory under this integration
folder with `--out-dir`, for example
`runs/issues/S02/recovery18_20261029/integration/v3_output_retry_01`.

The output is a computational self-check only. Hashing the registered PDFs
confirms file identity against the collection ledger; it does not validate
extracted values against page content. External source review remains required,
and S03 remains locked.

Adapter boundary tests use synthetic rows and do not run S00 or S02:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B `
  runs/issues/S02/recovery18_20261029/integration/test_comparability_adapter.py

Runner scope and rule-lock boundary tests also use synthetic rows and do not
run S00 or S02:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B `
  runs/issues/S02/recovery18_20261029/integration/test_rebuild_v3.py
```

## Independent S02 replay handoff

`replay_metrics_v3.py` replays S02 from the completed v3 normalized gzip. It
uses the gzip, rules file, scope-hold spec, adapter and tool hashes fixed in the
v3 `recovery18_manifest.json`. It does not load the 360 source extraction JSONs
or read source PDFs. It verifies the scope tags and derived OCF hold in the
normalized input, installs the same S01 input adapter during S02, then requires
byte and full-field equality for both canonical v3 `all_pool_metrics.csv` and
`company_metric_summary.csv`. The replay output is isolated and refuses to
overwrite an existing directory. The result is a computational `SELF_CHECK`;
source-page review remains unperformed and S03 remains locked.

The runner locally replaces only the stale `Q16` explanatory note about annual
report-only extraction. It records that S00 already covered all 12 slots and
that this round addresses remaining layout, unit, entity, restatement, and
scope issues. The Q16 QC result and all scientific calculations stay unchanged;
the replay applies the same note from the v3 manifest.

After the v3 source package and manifest are frozen, run from the repository
root:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B `
  runs/issues/S02/recovery18_20261029/integration/replay_metrics_v3.py --execute
```

An alternate frozen manifest or fresh integration output child can be selected
with `--v3-manifest` and `--out-dir`.

Replay boundary tests use synthetic CSV rows only:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B `
  runs/issues/S02/recovery18_20261029/integration/test_replay_metrics_v3.py
```
```
