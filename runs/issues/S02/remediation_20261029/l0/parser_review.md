# A03 parser read-only review

Reviewed `tools/a03_financial_field_extractor.py` at SHA-256 `afe1e1be721785e5abe31da4169fe0f420a3e73410d058b32a2750dcf73704c0`. This was a function-level review only; no parser edits and no batch run. The current `summary_cells` and the already identified summary-table annotation, NA placeholder, and cross-page unit changes were not re-audited here.

## Reproduced failure modes

1. **A blank target row can take the next row's value when `use_merge=True`.** In `extract_statement_field`, spans 1–5 are tried after a one-line blank match. The joined string still starts with the requested label, and the code returns the first later number without checking whether it belongs to that row. Calling `extract_statement_field(["净利润\n归属于母公司股东的净利润 1,234.56 900.00"], {"IS_CONS": (0, 0, None)}, "IS_CONS", "FIN.NP.YTD", ["净利润"], True)` returns `('1,234.56', 1, '净利润', None)`. That assigns attributable net profit to the separate `净利润` field. A row boundary or an explicit continuation-label check is needed before joining a blank row to the next row.

2. **A small annotation can become the extracted amount when one period is blank.** `statement_amounts` removes an unformatted small integer only when at least three numeric tokens were found. Since em dashes are ignored as numbers, `extract_statement_field(["营业收入 注3 — 900.00"], {"IS_CONS": (0, 0, "万元")}, "IS_CONS", "FIN.REV.YTD", ["营业收入"], True)` returns `('3', 1, '营业收入', None)` instead of `900.00`. The standalone parser call returns `[('3', 3.0), ('900.00', 900.0)]`. This is a concrete wrong-value path for a row with a note number, one available period and a blank/dash in the other period.

3. **Parentheses are sign-sensitive to exact spacing and punctuation.** Plain accounting negatives such as `(1,000.00)` parse correctly. But `statement_amounts("营业收入 ( 1,000.00 ) ( 900.00 )")` returns both values as positive because the number regex does not include whitespace inside the parentheses. If PDF text extraction emits those spaces, a negative becomes positive. A separate form, `statement_amounts("营业收入 (-1,000.00) (900.00)")`, raises `ValueError: could not convert string to float: '--1000.00'`. In `extract_one`, the parallel runner converts that exception into `WORKER_FAILED`; the serial path calls `extract_one` without a catch and aborts the run. These cases are reproduced from text inputs; I did not verify that either formatting occurs in a current source PDF.

## Column-order boundary

`extract_statement_field` always selects `vals[0]`; it does not inspect the table header to establish which numeric column is consolidated. The fixture `pages=["项目 母公司 合并\n营业收入 100 1000"]`, region `IS_CONS=(0,0,None)`, returns `100` for `FIN.REV.YTD`. This only becomes a wrong value if an accepted combined table places the parent-company column first. I did not verify a reversed-order report in the local readable materials, so this is an unverified input boundary rather than a confirmed current-pool error. The parser is safe only while the invariant “consolidated is always the first numeric column” holds for every combined statement it accepts; it currently does not validate that invariant.

The fixture calls used the existing parser functions directly and did not modify input or launch extraction batches.
