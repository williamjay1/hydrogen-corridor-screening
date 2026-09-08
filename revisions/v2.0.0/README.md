# Version 2.0.0: capacity and connectivity bounds

This reproducibility release supports *Capacity and Connectivity Bounds for European Hydrogen Import Corridors*. It is a major model and population revision. Do not combine its outputs with the earlier interface-verification screen.

## Run from the archived derived data

Python 3.12 was used. Install `requirements.txt`, then from this directory run:

```sh
python src/strengthen.py
python src/extend_checks.py
python src/joint_bounds.py
python src/make_figures.py
python src/final_checks.py
```

The scripts read only the included derived CSV files and write local runs, audits, figures and previews. They work without the authors' drives or a website login. The full joint calculation enumerates 259200 extreme endpoint assignments; it can take several minutes. Nine figures are vector PDF with embedded fonts and also 900 dpi PNG. Input and frozen output hashes are in `manifest.json`.

## Evidence boundary

The main graph freezes ENTSOG TYNDP 2024: 167 directed backbone pairs, two horizons, nine eligible terminal groups and 22 positive-demand EU countries retained before reachability filtering. Carrier supply uses a shared country pool and the last eligible project phase. National endpoint accounting is relaxed for the upper bound and assigned to individual recorded nodes for the joint lower bound. These are annual planning bounds conditional on capacity availability, not observed operating throughput, confidence intervals, investment recommendations, or European shortage forecasts.

Twelve scenarios cover two horizons, two infrastructure levels and three industry-demand quantiles. All 511 nonempty terminal subsets are enumerated. Capacity ranking matches the optimistic optimum. All six optimistic four-interface optima and all 77 central-scenario optima are disclosed; the mapping-aware set is itself one optimistic optimum. The separate 2026 carrier refresh retains the 2024 graph and unmatched projects and must not be treated as a synchronized 2026 forecast.

## Raw-source verification

Raw third-party workbooks and full website copies are not redistributed. Obtain the four named files in `audits/raw_file_integrity.json` from `data/upstream_source_manifest.csv`, preserving their source terms. Set `PROJECT16_RAW_DIR` to a folder with `tyndp/` and `eho/` subfolders and run `python src/verify_raw_sources.py`. This rechecks frozen edge and carrier records against the cited workbook cells and recomputes the demand weights/scenarios. The default computation does not require this optional download. The 2026 project extraction is included as derived data; source sheet and semantics are retained. See `docs/SOURCE_NOTES.md`.

## Changes from v1.0.1

The previous implementation's excluded demand, interface-verification interpretation and numeric results do not apply. Version 2 retains disconnected national demand; replaces verification-budget claims with interface-cardinality comparisons; evaluates endpoint assignment uncertainty; distinguishes source and network vintages; and reports complete optimal tie sets. The supported contribution is a measured diagnosis of capacity/connectivity evidence, not a new flow algorithm or a claim of publication readiness.

The repository/archive creator remains Junjie Zhang, as in v1.0.1. Manuscript authors remain Ruojun Duan and Junjie Zhang; repository authorship does not replace the manuscript author list. Final submission files are distributed separately after insertion of the minted version DOI. No internal editorial reports are required to run this release.
