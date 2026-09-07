# Public-data hydrogen corridor screening

This directory is the independent IEEE Access redesign package for the manuscript *A Decision Support Tool for Prioritizing Hydrogen Import Interface Verification with Public European Infrastructure Data*.

## Scope

The package implements a bounded engineering screen for terminal--carrier and terminal--backbone interfaces. Binary variables select interfaces for priority verification; they do not represent construction, permitting, ownership, CAPEX, or optimal investment. The model uses public, versioned records and explicitly excludes unsupported endpoints, capacities, status years, and direct-ammonia sinks.

The active frozen data vintage is ENTSOG TYNDP 2024. TYNDP 2026 Draft is not mixed into the main sample. Public source pages are retained in `data/corridor_2024/source_manifest.csv` and the extended run manifest, and include:

- [TYNDP 2024 downloads](https://tyndp2024.entsog.eu/downloads/)
- [TYNDP 2024 Hydrogen input archive](https://2024-data.entsog-tyndp-scenarios.eu/files/scenarios-inputs/Hydrogen.zip)
- [TYNDP 2024 IGI indicators](https://tyndp2024.entsog.eu/h2igi-report/infrastructure-gaps-identification-igi-indicators/)
- [European Hydrogen Observatory demand](https://observatory.clean-hydrogen.europa.eu/hydrogen-landscape/end-use/hydrogen-demand)
- [Clean Hydrogen Partnership port study](https://www.clean-hydrogen.europa.eu/media/publications/study-hydrogen-ports-and-industrial-coastal-areas-reports_en)
- [European Hydrogen Backbone roadmap](https://ehb.eu/files/downloads/1712733755_EHB-Implementation-Roadmap-Public-support-as-catalyst-for-hydrogen-infrastructure.pdf)
- [Natural Earth 1:110m country outlines](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson) (visual backdrop only)

Oversized or restricted upstream bundles are not redistributed. This repository contains the derived public data products, source metadata, model code, and audit outputs. Original downloads should be obtained from the linked official sources under their applicable terms.

The external Hydrogen import-generator workbook used for the face-validity check is not redistributed in this repository. The diagnostic can be rerun after the authorized workbook is obtained; see `data/external/README.md` for the source reference and expected filename.

## Environment

- Windows PowerShell
- Python 3.11 or later
- `numpy`, `pandas`, `scipy`, `matplotlib`, `Pillow`
- A LaTeX installation with the included IEEE Access class for manuscript compilation

## Run the diagnostic

From the project root:

```powershell
python src\go_diagnostic.py --output runs\corridor_2024\go_diagnostic_20260907 --random-draws 200
```

The run writes the scenario matrix, flow results, interface priority and criticality, exact equal-budget portfolio baseline, structural ablation, evidence-gap diagnostics, N--1/N--2 failure stress diagnostics, capacity sensitivity, external corridor-face check, gate results, and `decision.json`.

The final frozen run reports:

- selected interfaces: Belgium, Germany, northern France, and the Netherlands;
- worst planning-scenario curtailment: 55.7161%;
- equal-budget portfolio median: 77.8947%;
- N--1 failure stress worst curtailment: 77.8947%;
- N--2 failure stress worst curtailment: 92.3792%;
- capacity-evidence removal regret: 22.1053 percentage points;
- all active diagnostic gates: PASS.

The scenario based robust and deterministic selections coincide in this data product. The package therefore reports parity rather than a scenario based robust superiority premium.

A supporting verification-budget run is also stored at runs\corridor_2024\go_diagnostic_budget6_20260907. It selects the four core groups plus the documented German and Polish candidates and retains the 55.7161% worst planning-scenario rate. The budget is a verification-resource control, not a construction budget.

## Figure design and export

The manuscript figures were reworked as publication graphics rather than
diagnostic screenshots. The design audit consulted the public
[SciencePlots repository](https://github.com/garrettj403/SciencePlots) for
scientific plotting conventions, including restrained colour use, direct
value annotation, quiet axes, and consistent typography. The repository
informed style principles only; the figure code and all plotted values remain
local and auditable.

Each figure is exported as a 900 dpi PNG for the IEEE Access manuscript and as
an editable PDF counterpart. Multi-panel figures use direct labels and shared
visual encodings. Figure 2 uses the Natural Earth backdrop only for geographic
orientation; the graph anchors are not physical pipe coordinates.

## Run tests and figures

```powershell
python -m unittest tests.test_corridor_milp tests.test_go_diagnostic -v
python src\make_go_figures.py --run runs\corridor_2024\go_diagnostic_20260907 --output outputs\ieeeaccess_corridor_redesign\go_version_20260907\figures
```

The expected test result is 12 passed tests. Eight figures are exported at
approximately 900 dpi for the manuscript, with vector PDF counterparts.
Figure 2 uses the Natural Earth file only as a light country-outline backdrop;
the frozen graph table provides country labels but no endpoint coordinates, so
plotted anchors are for geographic context and graph lines are not pipe
geometries.

## Compile the manuscript

The manuscript source is `IEEE_ACCESS_CORRIDOR_GO_DRAFT.tex`. With the included template files in the same directory, compile twice with:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error IEEE_ACCESS_CORRIDOR_GO_DRAFT.tex
pdflatex -interaction=nonstopmode -halt-on-error IEEE_ACCESS_CORRIDOR_GO_DRAFT.tex
```

The final source/PDF pair is 13 pages. The reference list follows the order of first citation in the text, and every figure, table, and numbered equation is cited in the main text. LaTeX may report underfull boxes from long web references and the IEEE Access template; no fatal compilation error is expected.

## Interpretation boundary

The results are annual public-data stress metrics. They are not observed port throughput, queueing, hourly pipeline utilization, conversion efficiency, commercial availability, reliability probabilities, project finance, or an optimal construction program. The external TYNDP Hydrogen comparison is a partial corridor-face check, not IGI replication. Any future operational or investment claim requires named terminal crosswalks, firm capacity evidence, storage and temporal constraints, and independently validated local delivery routes.
