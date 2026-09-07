# 2026-09-07 — active path card for the redesigned IEEE Access package

| Field | Active decision |
|---|---|
| Target journal / route | IEEE Access, applied engineering Research Article route; ISSN 2169-3536 |
| Contribution type | Auditable public-data project-graph and robust-MILP interface-screening tool |
| Research question | Which terminal--carrier and terminal--backbone interfaces should receive priority verification when public records are incomplete and planning conditions vary? |
| Analysis unit | Directed terminal/backbone graph flow and facility demand-accounting sink, annual GWh |
| Population and sample | European public-data corridor product: 69 nodes, 356 directed edges, 22 interface rows, 9 candidate groups, 20 carrier records, 55 facilities |
| Main evidence | ENTSOG TYNDP 2024, EHO demand records, official corridor inputs, port-study context, source manifest, exclusion ledger, executed result CSVs |
| Comparators | Star LP, project-graph LP, carrier-compatible LP, deterministic four-interface MILP, robust four-interface MILP; exact 126-portfolio census |
| Success criteria | 100% traceability; positive portfolio discrimination; at least 1 pp evidence-gap regret; robust N--1 noninferiority; monotone capacity response; top-four external corridor-face overlap in both years |
| Highest supported claim | A four-interface verification portfolio can be selected and stress-tested reproducibly under the frozen public-data product; capacity evidence is the dominant detected information bottleneck |
| Design modules | H Algorithm/engineering, I Data product, B external face check, plus reproducibility and failure-stress validation |
| Status | **GO, bounded**: all active diagnostic gates pass; no operational, investment-optimality, or IGI replication claim |

The 2026-09-04 NO-GO card below is retained as a historical record for a different full-scope validation design.

# 2026-09-04 corridor redesign path card

**Target:** IEEE Access Applied Research; EI-led, SCI-compatible engineering optimization.

**Research question:** Can auditable public terminal, backbone, carrier, and facility data select a carrier-compatible verification portfolio whose import-corridor service is more robust than an equal-budget deterministic selection?

**Analysis unit:** Directed terminal-to-backbone and backbone corridor edge; facility demand-accounting sink; annual GWh.

**Core evidence:** TYNDP 2024 Annex A/C2, H2 IGI, official maps, EHO demand inventory/forecast, and Clean Hydrogen Partnership port study.

**Design path:** H + I, with external benchmark and N-1 stress tests. No causal, operations, investment, or real-time dispatch claim.

**Status:** **NO-GO.** Traceability and capacity coverage pass, but IGI alignment and robust gain fail in both full and predeclared fallback scopes. The active decision record is [CORRIDOR_REDESIGN_STATUS.md](CORRIDOR_REDESIGN_STATUS.md).

# Project 16 path card

## Active 2026-09-01 route

The active manuscript is an IEEE Access Research Article. The former IJHE route is retained below as historical project evidence only.

| Field | Final decision |
|---|---|
| Target route | SCIE energy, hydrogen, engineering and sustainable technology assessment journals |
| Primary target | IEEE Access, Research Article; source/PDF package ready for portal entry, subject to account-side ORCID and live ISSN/MJL confirmation |
| Contribution type | Public-data engineering capacity-stress model for hydrogen-carrier portfolio screening |
| Geography | EU-27 demand nodes and selected EU ports only |
| Excluded | UK, Norway and Switzerland; no silent institutional pooling |
| Analysis unit | Annual port-mode-demand-class-carrier flow in a scenario |
| Population | 22 active EU-27 demand nodes and nine selected ports with public evidence; not all EU ports |
| Decision variables | Carrier flows and unmet demand; capacity envelopes are scenario constraints rather than investment decisions |
| Main evidence | EHO, Eurostat, ENTSOG, public project pages, GISCO/OSM/TEN-T and public parameter priors |
| Benchmarks | Unconstrained lower bound, planned central, port stress, inland stress, joint stress, carbon-price diagnostic and controlled maturity-activity-inland interaction diagnostic |
| Highest supportable claim | Under the documented public-data envelopes, the joint maturity and activity-pressure condition activates non-ammonia carriers relative to the lower bound, while conservative inland availability amplifies the portfolio response; this is a conditional model result, not observed congestion or a causal estimate |
| Forbidden claims | Observed queues, realised pipeline use, measured terminal throughput, universal EU ranking, causal policy effect, audited financial case or full ISO LCA |
| Final status | Original measured-congestion framing rejected; current public-data paper is a bounded IEEE Access Research Article package; novelty confidence medium-low with residual similarity risk; local final gate 50/50 |

## Mandatory modules

- Engineering/system model: PASS for declared LP.
- Public-data audit: PASS with proxy boundary.
- Literature/gap audit: pass for the bounded contribution; residual similarity risk remains medium-high.
- Uncertainty and robustness: PASS for declared 300-draw and scenario layer.
- Physical operational validation: unavailable and explicitly not claimed.

## Current package and quality ceiling

- Active package: `IEEE_ACCESS_CORRIDOR_GO_DRAFT.tex` and `IEEE_ACCESS_CORRIDOR_GO_DRAFT.pdf`.
- Quality ceiling: Applied Energy. The paper is not routed there because the model has no observed operational validation, firm multimodal topology, or project-level finance.
- Practical backup: Sustainable Energy Technologies and Assessments.
- IEEE Access guide checks: official double-column template, Research Article route, 3--10 keywords, matching source/PDF, data-supported conclusions, AI disclosure, and upload-time author metadata.
