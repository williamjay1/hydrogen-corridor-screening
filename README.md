# Capacity and Connectivity Bounds for European Hydrogen Import Corridors

**Current release: v2.0.0.** Start at [`revisions/v2.0.0/README.md`](revisions/v2.0.0/README.md) for the self-contained derived-data workflow, frozen results and nine scientific figures.

This public research archive quantifies how planning capacities, directed transmission connections, unresolved source/demand assignments and project vintages change a hydrogen import service envelope. The main graph is frozen TYNDP 2024; matched 2026 carrier records are a separately labelled sensitivity. The code does not establish actual operating throughput or optimal investment.

The current implementation enumerates all 511 nonempty terminal subsets and 259200 joint endpoint assignments. It reports all relevant optimal ties and the cases where capacity ranking already matches the optimum. It includes raw-source locators, directed-capacity checks, independent linear programming validation and reproducible vector/900 dpi figures.

## Version history and citation

Version 2.0.0 is a major model revision. The previous version DOI [10.5281/zenodo.22647942](https://doi.org/10.5281/zenodo.22647942) identifies **v1.0.1 only** and must not be cited as reproducing v2 results. A new archive version is generated from this release through the existing GitHub–Zenodo integration. Its DOI will be added once the published record is verified.

The original root-level code, runs, figures and `IEEE_ACCESS_CORRIDOR_GO_DRAFT` files are retained solely as **historical v1 material**. Their results and earlier readiness labels are superseded; they are not the active manuscript or execution entry point. The original README is preserved at `docs/README_v1.0.1_historical.md`.

Archive creator: Junjie Zhang. Manuscript authors: Ruojun Duan and Junjie Zhang. These roles remain distinct. Public archiving is not a claim of journal acceptance or submission clearance.
