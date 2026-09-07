# IEEE Access redesign status — 7 September 2026

## Decision

**GO, bounded.** The independent package is ready for author review and final submission preparation for IEEE Access. The decision applies to a public-data engineering tool for hydrogen-import corridor interface screening. It does not imply journal acceptance and does not support claims about realized throughput, operational reliability, project finance, optimal construction, or replication of the TYNDP IGI hotspot construct.

The previous 4 September NO-GO is preserved in the historical ledgers. It applied to a different question that demanded full IGI alignment and a numerical robust premium. The present redesign changes the estimand, records the robust/deterministic equality, and uses an evidence-prioritization validation protocol.

## Active manuscript and run

- Manuscript source: `IEEE_ACCESS_CORRIDOR_GO_DRAFT.tex`
- Manuscript PDF: `IEEE_ACCESS_CORRIDOR_GO_DRAFT.pdf`
- Frozen run: `runs/corridor_2024/go_diagnostic_20260907`
- Core model: `src/go_diagnostic.py`
- Figures: `figures/`
- Tests: `tests/test_corridor_milp.py` and `tests/test_go_diagnostic.py`

Supporting budget run: runs/corridor_2024/go_diagnostic_budget6_20260907.

## Data and evidence boundary

The frozen data product contains 69 graph nodes, 356 directed backbone edges, 22 explicit terminal-interface rows, 9 consolidated interface candidates, 20 carrier-project records, 15 country--carrier pools, 55 industrial facilities, and 330 facility-scenario demand rows. All included inputs have source-manifest entries. Missing endpoint, capacity, status-year, or compatibility evidence is excluded or retained only in the exclusion ledger. Direct ammonia remains ineligible because the available EHO category does not verify a named direct-ammonia sink.

The main data vintage is ENTSOG TYNDP 2024. TYNDP 2026 Draft is not mixed into the core sample. External TYNDP Hydrogen import-generator records are used only for a corridor-face check. EHO demand records provide scenario envelopes; they are not measurements of future offtake.

## Executed gates

| Gate | Threshold | Observed result | Status |
|---|---|---:|---|
| Asset traceability | 100% of included corridor inputs | 100% | PASS |
| Equal-budget discrimination | Selected worst DCR below random median and Q90 | 55.7161% versus 77.8947% median and 100% Q90 | PASS |
| Evidence-gap detectability | At least 1 percentage point regret after capacity evidence removal | 22.1053 percentage points | PASS |
| N--1 noninferiority | Robust worst DCR no worse than deterministic | 77.8947% versus 77.8947% | PASS |
| Capacity response | Higher capacity cannot increase worst DCR | 77.8580%, 55.7161%, 33.5741% at 0.5, 1.0, 1.5 | PASS |
| External corridor face | At least 2 of 4 top countries overlap in each year | 2 in 2030 and 2 in 2040 | PASS |

The robust and deterministic selections are identical: Belgium, Germany, northern France, and the Netherlands. This is an observed boundary of the frozen product, not evidence of universal robust superiority.

A supporting budget-6 run selects the same four core groups plus the documented German and Polish candidate groups and retains the 55.7161% worst planning-scenario rate. This is used only to illustrate verification-resource expansion. Figure 2 uses a Natural Earth 1:110m country-outline asset as a visual backdrop; the model uses no map coordinates or map-derived capacities.

## Main stress results

- Worst planning-scenario demand curtailment: 55.7161%.
- Mean planning-scenario demand curtailment: 21.5125%.
- Total planning-scenario unmet demand: 358,030.19 GWh.
- Worst held-out N--1 curtailment: 77.8947%.
- Worst held-out N--2 curtailment: 92.3792%.
- Removing capacity evidence raises held-out N--1 worst curtailment to 100%, producing 22.1053 percentage points of regret.
- Selected interface N--1 deltas: Netherlands 22.18 percentage points, Belgium 14.48, Germany 7.62, northern France 0.00 in the tested matrix.

These quantities are deterministic scenario outputs and stress-test metrics. They are not probabilities, confidence intervals, observed utilization, or forecasts.

## Reviewer-2 boundaries

The remaining major limitation is evidence resolution. Anonymous country--carrier pools and facility accounting links are conservative screening constructs, not named terminal contracts or local delivery routes. The next engineering data request is a terminal-to-project crosswalk with firm capacity, storage, conversion, and local route evidence. The paper already states that this work is a screening and data-collection tool rather than an investment plan.

## Final checks

- 12/12 unit and deterministic-rerun tests pass.
- The source compiles to 12 pages and remains below the 20-page target.
- The package includes eight publication figures rendered at approximately 900 dpi, the source manifest, result CSVs, code, tests, manuscript source, and PDF.
- The old validation draft and old NO-GO memo remain untouched.
