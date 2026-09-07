"""Two-stage lexicographic robust MILP for the audited TYNDP 2024 graph.

First-stage binary variables identify terminal-carrier and terminal-backbone
interfaces that should receive priority engineering verification.  They do
not mean that a project is built, financed, contracted, or available in real
operation.  Second-stage flows are scenario-specific recourse decisions.

The model has no unmet-demand penalty.  It solves the stated lexicographic
objectives in order: worst demand-cut rate, total unmet demand, and interface
count.  Cost is deliberately not part of the optimisation because Annex A/C2
do not supply a harmonised, auditable service-cost schedule.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, OptimizeResult, milp
from scipy.sparse import lil_matrix


PROJECT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("P16_CORRIDOR_DATA_DIR", str(PROJECT / "data" / "corridor_2024")))
TOLERANCE = 1.0e-7


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    year: int
    level: str
    demand_level: str


@dataclass
class BuiltProblem:
    c: np.ndarray
    integrality: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    constraints: LinearConstraint
    variable_index: dict[tuple[Any, ...], int]
    metadata: dict[str, Any]


@dataclass
class SolveBundle:
    result: OptimizeResult
    problem: BuiltProblem
    objective_name: str


@dataclass
class LexicographicResult:
    stages: dict[str, SolveBundle]
    final: SolveBundle
    selected_terminal_carriers: set[str]
    selected_terminal_backbones: set[str]


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _terminal_backbone_key(edge: pd.Series | Mapping[str, Any]) -> str:
    return f"{edge['from_node']}|{edge['to_node']}"


def _terminal_carrier_key(terminal_node: str, carrier: str) -> str:
    return f"{terminal_node}|{carrier}"


class CorridorMILP:
    """Read the derived data product and build reproducible LP/MILP problems."""

    def __init__(self, data_dir: Path | str = DATA) -> None:
        self.data_dir = Path(data_dir)
        required = {
            "edges": "network_edges.csv",
            "interfaces": "terminal_carrier_interfaces.csv",
            "carrier_pools": "carrier_country_pools.csv",
            "facilities": "industrial_facilities.csv",
            "demands": "facility_scenario_demands.csv",
            "scenarios": "demand_scenarios.csv",
        }
        missing = [filename for filename in required.values() if not (self.data_dir / filename).exists()]
        if missing:
            raise FileNotFoundError(f"Missing corridor data tables in {self.data_dir}: {missing}")
        self.edges = pd.read_csv(self.data_dir / required["edges"])
        self.interfaces = pd.read_csv(self.data_dir / required["interfaces"])
        self.carrier_pools = pd.read_csv(self.data_dir / required["carrier_pools"])
        self.facilities = pd.read_csv(self.data_dir / required["facilities"])
        self.demands = pd.read_csv(self.data_dir / required["demands"])
        self.demand_scenarios = pd.read_csv(self.data_dir / required["scenarios"])
        self._clean_frames()

    def _clean_frames(self) -> None:
        self.edges["year"] = self.edges["year"].astype(int)
        self.edges["capacity_pci_pmi_gwh_per_day"] = pd.to_numeric(
            self.edges["capacity_pci_pmi_gwh_per_day"], errors="coerce"
        ).fillna(0.0)
        self.edges["capacity_advanced_gwh_per_day"] = pd.to_numeric(
            self.edges["capacity_advanced_gwh_per_day"], errors="coerce"
        ).fillna(0.0)
        self.interfaces["year"] = self.interfaces["year"].astype(int)
        self.carrier_pools["year"] = self.carrier_pools["year"].astype(int)
        self.carrier_pools["carrier_evidence_capacity_gwh_per_day"] = pd.to_numeric(
            self.carrier_pools["carrier_evidence_capacity_gwh_per_day"], errors="coerce"
        ).fillna(0.0)
        self.demands["year"] = self.demands["year"].astype(int)
        self.demands["target_gwh_per_year"] = pd.to_numeric(
            self.demands["target_gwh_per_year"], errors="coerce"
        ).fillna(0.0)
        self.facilities["baseline_h2_gwh_per_year"] = pd.to_numeric(
            self.facilities["baseline_h2_gwh_per_year"], errors="coerce"
        ).fillna(0.0)
        self.carriers = tuple(sorted(self.interfaces["carrier_class"].dropna().unique().tolist()))
        if not self.carriers:
            raise ValueError("No traceable terminal carrier interfaces are available.")

    @staticmethod
    def core_scenarios() -> list[Scenario]:
        return [
            Scenario(f"S{year}_{level.replace('/', '')}_{demand}", year, level, demand)
            for year in (2030, 2040)
            for level in ("PCI/PMI", "Advanced")
            for demand in ("low", "medium", "high")
        ]

    def _capacity_column(self, level: str) -> str:
        if level == "PCI/PMI":
            return "capacity_pci_pmi_gwh_per_day"
        if level == "Advanced":
            return "capacity_advanced_gwh_per_day"
        raise ValueError(f"Unsupported infrastructure level {level!r}")

    def scenario_edges(
        self,
        scenario: Scenario,
        failed_edge_keys: Iterable[str] = (),
        star: bool = False,
    ) -> pd.DataFrame:
        """Return positive-capacity directed edges in a scenario, with GWh/y units."""
        capacity_column = self._capacity_column(scenario.level)
        frame = self.edges[self.edges["year"].eq(scenario.year)].copy()
        frame["capacity_gwh_per_year"] = frame[capacity_column] * 365.0
        frame = frame[frame["capacity_gwh_per_year"] > TOLERANCE].copy()
        failed = set(failed_edge_keys)
        frame["static_edge_key"] = frame.apply(
            lambda row: _terminal_backbone_key(row)
            if row["edge_type"] == "terminal_backbone"
            else f"{row['from_node']}|{row['to_node']}",
            axis=1,
        )
        if failed:
            frame = frame[~frame["static_edge_key"].isin(failed)].copy()
        if star:
            return frame[frame["edge_type"].eq("terminal_backbone")].copy()
        return frame

    def scenario_demands(self, scenario: Scenario) -> pd.DataFrame:
        frame = self.demands[
            self.demands["scenario_id"].eq(f"D{scenario.year}_{scenario.demand_level}")
        ].copy()
        if frame.empty:
            raise ValueError(f"No demand records for {scenario}")
        return frame.merge(
            self.facilities[["facility_id", "country", "end_use"]],
            on=["facility_id", "country"],
            how="left",
            validate="many_to_one",
        )

    def carrier_lookup(self, scenario: Scenario) -> dict[str, set[str]]:
        """Map C2 terminal edge IDs to source-supported carrier classes."""
        frame = self.interfaces[self.interfaces["year"].eq(scenario.year)]
        lookup: dict[str, set[str]] = {}
        for _, row in frame.iterrows():
            lookup.setdefault(_text(row["terminal_edge_id"]), set()).add(_text(row["carrier_class"]))
        return lookup

    def source_has_any_carrier(self, scenario: Scenario) -> set[str]:
        return set(self.carrier_lookup(scenario))

    def carrier_pool_lookup(self, scenario: Scenario) -> dict[tuple[str, str], float]:
        """Return shared Annex-A country-carrier capacities for one horizon.

        The pool is an auditable upper bound at country-terminal-group level,
        not a named project-to-C2-node assignment.  It prevents evidence for a
        carrier project from being replicated over multiple C2 terminal groups.
        """
        frame = self.carrier_pools.loc[self.carrier_pools["year"].eq(scenario.year)]
        return {
            (_text(row["country"]), _text(row["carrier_class"])): float(
                row["carrier_evidence_capacity_gwh_per_day"]
            )
            for _, row in frame.iterrows()
        }

    def available_interface_keys(self, scenarios: Sequence[Scenario]) -> tuple[set[str], set[str]]:
        carrier_keys: set[str] = set()
        backbone_keys: set[str] = set()
        for scenario in scenarios:
            edges = self.scenario_edges(scenario)
            lookup = self.carrier_lookup(scenario)
            for _, edge in edges[edges["edge_type"].eq("terminal_backbone")].iterrows():
                if edge["edge_id"] not in lookup:
                    continue
                backbone_keys.add(_terminal_backbone_key(edge))
                for carrier in lookup[edge["edge_id"]]:
                    carrier_keys.add(_terminal_carrier_key(edge["from_node"], carrier))
        return carrier_keys, backbone_keys

    def _scenario_carriers(self, compatibility: bool) -> tuple[str, ...]:
        return self.carriers if compatibility else ("H2_generic",)

    def _terminal_flow_allowed(
        self,
        edge: pd.Series,
        carrier: str,
        lookup: Mapping[str, set[str]],
        compatibility: bool,
        selected_carriers: set[str] | None,
        selected_backbones: set[str] | None,
    ) -> bool:
        source_key = _terminal_backbone_key(edge)
        if selected_backbones is not None and source_key not in selected_backbones:
            return False
        supported = lookup.get(_text(edge["edge_id"]), set())
        if not supported:
            return False
        if compatibility:
            carrier_key = _terminal_carrier_key(_text(edge["from_node"]), carrier)
            if carrier not in supported:
                return False
            if selected_carriers is not None and carrier_key not in selected_carriers:
                return False
        return True

    def build_problem(
        self,
        scenarios: Sequence[Scenario],
        *,
        objective: str,
        binary_interfaces: bool,
        compatibility: bool = True,
        selected_carriers: set[str] | None = None,
        selected_backbones: set[str] | None = None,
        failed_edge_keys: Iterable[str] = (),
        fix_worst_dcr: float | None = None,
        fix_total_unmet: float | None = None,
        interface_budget: int | None = None,
    ) -> BuiltProblem:
        """Build a scenario-expanded multi-commodity flow LP/MILP.

        `selected_*` turn the binary stage into fixed recourse selection.  This
        is used for deterministic out-of-sample evaluation and N-1 tests.
        """
        if not scenarios:
            raise ValueError("At least one scenario is required")
        scenario_carriers = self._scenario_carriers(compatibility)
        failed = set(failed_edge_keys)
        var: dict[tuple[Any, ...], int] = {}
        lower: list[float] = []
        upper: list[float] = []
        integrality: list[int] = []

        def add_var(key: tuple[Any, ...], lb: float = 0.0, ub: float = math.inf, integer: bool = False) -> int:
            if key in var:
                return var[key]
            idx = len(var)
            var[key] = idx
            lower.append(lb)
            upper.append(ub)
            integrality.append(1 if integer else 0)
            return idx

        # First-stage keys must exist before constraint construction.  A
        # terminal interface that exists only in 2040 may be selected but has
        # zero 2030 recourse capability, exactly as the input years imply.
        all_carrier_keys, all_backbone_keys = self.available_interface_keys(scenarios)
        if selected_carriers is not None:
            all_carrier_keys &= set(selected_carriers)
        if selected_backbones is not None:
            all_backbone_keys &= set(selected_backbones)
        if binary_interfaces:
            for key in sorted(all_carrier_keys):
                add_var(("y", key), 0.0, 1.0, True)
            for key in sorted(all_backbone_keys):
                add_var(("z", key), 0.0, 1.0, True)

        metadata: dict[str, Any] = {
            "scenarios": {},
            "carrier_keys": sorted(all_carrier_keys),
            "backbone_keys": sorted(all_backbone_keys),
            "binary_interfaces": binary_interfaces,
            "compatibility": compatibility,
            "failed_edge_keys": sorted(failed),
        }
        # Register recourse variables.
        for scenario in scenarios:
            edges = self.scenario_edges(scenario, failed)
            demand = self.scenario_demands(scenario)
            lookup = self.carrier_lookup(scenario)
            carrier_pools = self.carrier_pool_lookup(scenario)
            backbone_nodes = set(edges.loc[edges["edge_type"].eq("backbone"), "from_node"]).union(
                set(edges.loc[edges["edge_type"].eq("backbone"), "to_node"])
            )
            backbone_nodes.update(edges.loc[edges["edge_type"].eq("terminal_backbone"), "to_node"].tolist())
            nodes_by_country: dict[str, list[str]] = {}
            for node in sorted(backbone_nodes):
                country = _text(
                    pd.concat(
                        [
                            edges.loc[edges["from_node"].eq(node), "from_country"],
                            edges.loc[edges["to_node"].eq(node), "to_country"],
                        ]
                    ).dropna().iloc[0]
                )
                nodes_by_country.setdefault(country, []).append(node)
            metadata["scenarios"][scenario.scenario_id] = {
                "edges": edges,
                "demand": demand,
                "carrier_lookup": lookup,
                "carrier_pools": carrier_pools,
                "backbone_nodes": sorted(backbone_nodes),
                "nodes_by_country": nodes_by_country,
                "total_demand": float(demand["target_gwh_per_year"].sum()),
            }
            for _, edge in edges.iterrows():
                for carrier in scenario_carriers:
                    if edge["edge_type"] == "terminal_backbone" and not self._terminal_flow_allowed(
                        edge,
                        carrier,
                        lookup,
                        compatibility,
                        selected_carriers,
                        selected_backbones,
                    ):
                        continue
                    add_var(("f", scenario.scenario_id, _text(edge["edge_id"]), carrier))
            for _, facility in demand.iterrows():
                for node in nodes_by_country.get(_text(facility["country"]), []):
                    for carrier in scenario_carriers:
                        add_var(("q", scenario.scenario_id, _text(facility["facility_id"]), node, carrier))
                add_var(("u", scenario.scenario_id, _text(facility["facility_id"])))
        worst_idx = add_var(("v",), 0.0, 1.0)

        # Constraints are added as sparse coefficient dictionaries first.
        rows: list[dict[int, float]] = []
        lbs: list[float] = []
        ubs: list[float] = []

        def add_constraint(coefficients: Mapping[int, float], lb: float = -math.inf, ub: float = math.inf) -> None:
            rows.append(dict(coefficients))
            lbs.append(lb)
            ubs.append(ub)

        for scenario in scenarios:
            info = metadata["scenarios"][scenario.scenario_id]
            edges: pd.DataFrame = info["edges"]
            demand: pd.DataFrame = info["demand"]
            nodes_by_country: dict[str, list[str]] = info["nodes_by_country"]
            lookup: dict[str, set[str]] = info["carrier_lookup"]
            # Directed-edge capacities are shared across carrier commodities.
            for _, edge in edges.iterrows():
                coeff: dict[int, float] = {}
                for carrier in scenario_carriers:
                    key = ("f", scenario.scenario_id, _text(edge["edge_id"]), carrier)
                    if key in var:
                        coeff[var[key]] = 1.0
                if coeff:
                    add_constraint(coeff, ub=float(edge["capacity_gwh_per_year"]))
                if binary_interfaces and edge["edge_type"] == "terminal_backbone":
                    backbone_key = _terminal_backbone_key(edge)
                    z_key = ("z", backbone_key)
                    if z_key not in var:
                        continue
                    for carrier in scenario_carriers:
                        f_key = ("f", scenario.scenario_id, _text(edge["edge_id"]), carrier)
                        if f_key not in var:
                            continue
                        add_constraint(
                            {var[f_key]: 1.0, var[z_key]: -float(edge["capacity_gwh_per_year"])},
                            ub=0.0,
                        )
                        if compatibility:
                            carrier_key = _terminal_carrier_key(_text(edge["from_node"]), carrier)
                            y_key = ("y", carrier_key)
                            if y_key in var:
                                add_constraint(
                                    {var[f_key]: 1.0, var[y_key]: -float(edge["capacity_gwh_per_year"])},
                                    ub=0.0,
                                )
            if compatibility:
                # Annex A capacity records are used only as shared
                # country/carrier upper bounds across anonymous C2 terminal
                # groups.  This makes carrier compatibility operational while
                # avoiding an unsupported named-project-to-node crosswalk.
                for (country, carrier), pool_capacity_daily in info["carrier_pools"].items():
                    coeff: dict[int, float] = {}
                    terminal_edges = edges.loc[
                        edges["edge_type"].eq("terminal_backbone")
                        & edges["from_country"].eq(country)
                    ]
                    for _, edge in terminal_edges.iterrows():
                        f_key = ("f", scenario.scenario_id, _text(edge["edge_id"]), carrier)
                        if f_key in var:
                            coeff[var[f_key]] = 1.0
                    if coeff:
                        add_constraint(coeff, ub=float(pool_capacity_daily) * 365.0)
            # Every facility is a demand sink at each documented backbone node
            # in its country.  The attachment has no asserted capacity or
            # route; it is a location-specific demand accounting arc.
            for _, facility in demand.iterrows():
                coeff: dict[int, float] = {}
                for node in nodes_by_country.get(_text(facility["country"]), []):
                    for carrier in scenario_carriers:
                        q_key = ("q", scenario.scenario_id, _text(facility["facility_id"]), node, carrier)
                        if q_key in var:
                            coeff[var[q_key]] = 1.0
                u_key = ("u", scenario.scenario_id, _text(facility["facility_id"]))
                coeff[var[u_key]] = 1.0
                add_constraint(coeff, lb=float(facility["target_gwh_per_year"]), ub=float(facility["target_gwh_per_year"]))
            # Commodity flow conservation at explicit backbone nodes only.
            for node in info["backbone_nodes"]:
                for carrier in scenario_carriers:
                    coeff: dict[int, float] = {}
                    for _, edge in edges.loc[edges["to_node"].eq(node)].iterrows():
                        f_key = ("f", scenario.scenario_id, _text(edge["edge_id"]), carrier)
                        if f_key in var:
                            coeff[var[f_key]] = coeff.get(var[f_key], 0.0) + 1.0
                    for _, edge in edges.loc[edges["from_node"].eq(node)].iterrows():
                        f_key = ("f", scenario.scenario_id, _text(edge["edge_id"]), carrier)
                        if f_key in var:
                            coeff[var[f_key]] = coeff.get(var[f_key], 0.0) - 1.0
                    for _, facility in demand.iterrows():
                        q_key = ("q", scenario.scenario_id, _text(facility["facility_id"]), node, carrier)
                        if q_key in var:
                            coeff[var[q_key]] = coeff.get(var[q_key], 0.0) - 1.0
                    if coeff:
                        add_constraint(coeff, lb=0.0, ub=0.0)
            # Worst demand-cut rate: sum(u_s) / D_s <= v.
            demand_total = float(info["total_demand"])
            coeff = {worst_idx: -demand_total}
            for facility_id in demand["facility_id"]:
                u_key = ("u", scenario.scenario_id, _text(facility_id))
                coeff[var[u_key]] = 1.0
            add_constraint(coeff, ub=0.0)

        if binary_interfaces:
            for carrier_key in all_carrier_keys:
                node = carrier_key.split("|", 1)[0]
                related = [key for key in all_backbone_keys if key.split("|", 1)[0] == node]
                if related:
                    # Carrier interface cannot be selected independently of a
                    # terminal-to-backbone interface; it is an audit pair.
                    add_constraint(
                        {var[("y", carrier_key)]: 1.0, **{var[("z", key)]: -1.0 for key in related}},
                        ub=0.0,
                    )
            if interface_budget is not None:
                coeff = {
                    **{var[("y", key)]: 1.0 for key in all_carrier_keys},
                    **{var[("z", key)]: 1.0 for key in all_backbone_keys},
                }
                add_constraint(coeff, ub=float(interface_budget))

        if fix_worst_dcr is not None:
            add_constraint({worst_idx: 1.0}, ub=float(fix_worst_dcr))
        if fix_total_unmet is not None:
            coeff = {
                idx: 1.0
                for key, idx in var.items()
                if key[0] == "u"
            }
            add_constraint(coeff, ub=float(fix_total_unmet))

        c = np.zeros(len(var), dtype=float)
        if objective == "worst_dcr":
            c[worst_idx] = 1.0
        elif objective == "total_unmet":
            for key, idx in var.items():
                if key[0] == "u":
                    c[idx] = 1.0
        elif objective == "interface_count":
            if not binary_interfaces:
                raise ValueError("Interface count objective requires binary interfaces")
            for key, idx in var.items():
                if key[0] in {"y", "z"}:
                    c[idx] = 1.0
        else:
            raise ValueError(f"Unknown objective {objective!r}")

        matrix = lil_matrix((len(rows), len(var)), dtype=float)
        for r, coefficients in enumerate(rows):
            for col, value in coefficients.items():
                matrix[r, col] = value
        return BuiltProblem(
            c=c,
            integrality=np.asarray(integrality, dtype=int),
            lower=np.asarray(lower, dtype=float),
            upper=np.asarray(upper, dtype=float),
            constraints=LinearConstraint(matrix.tocsr(), np.asarray(lbs), np.asarray(ubs)),
            variable_index=var,
            metadata=metadata,
        )

    def solve_problem(self, problem: BuiltProblem, objective_name: str) -> SolveBundle:
        result = milp(
            c=problem.c,
            integrality=problem.integrality,
            bounds=Bounds(problem.lower, problem.upper),
            constraints=problem.constraints,
            options={"disp": False, "mip_rel_gap": 0.0},
        )
        if not result.success:
            raise RuntimeError(f"{objective_name} solve failed: status={result.status}, message={result.message}")
        return SolveBundle(result=result, problem=problem, objective_name=objective_name)

    def solve_lexicographic(
        self,
        scenarios: Sequence[Scenario],
        *,
        compatibility: bool = True,
        interface_budget: int | None = None,
    ) -> LexicographicResult:
        """Run exact sequential objectives with only numerical closure tolerances."""
        if not scenarios:
            raise ValueError("At least one scenario is required")
        stage1 = self.solve_problem(
            self.build_problem(
                scenarios,
                objective="worst_dcr",
                binary_interfaces=True,
                compatibility=compatibility,
                interface_budget=interface_budget,
            ),
            "worst_dcr",
        )
        worst = float(stage1.result.fun)
        stage2 = self.solve_problem(
            self.build_problem(
                scenarios,
                objective="total_unmet",
                binary_interfaces=True,
                compatibility=compatibility,
                interface_budget=interface_budget,
                fix_worst_dcr=worst + TOLERANCE,
            ),
            "total_unmet",
        )
        total_unmet = float(stage2.result.fun)
        stage3 = self.solve_problem(
            self.build_problem(
                scenarios,
                objective="interface_count",
                binary_interfaces=True,
                compatibility=compatibility,
                interface_budget=interface_budget,
                fix_worst_dcr=worst + TOLERANCE,
                fix_total_unmet=total_unmet + max(TOLERANCE, total_unmet * 1.0e-9),
            ),
            "interface_count",
        )
        selected_carriers, selected_backbones = self.extract_selection(stage3)
        return LexicographicResult(
            stages={"worst_dcr": stage1, "total_unmet": stage2, "interface_count": stage3},
            final=stage3,
            selected_terminal_carriers=selected_carriers,
            selected_terminal_backbones=selected_backbones,
        )

    def solve_fixed_recourse(
        self,
        scenarios: Sequence[Scenario],
        *,
        selected_carriers: set[str],
        selected_backbones: set[str],
        compatibility: bool = True,
        failed_edge_keys: Iterable[str] = (),
    ) -> SolveBundle:
        problem = self.build_problem(
            scenarios,
            objective="total_unmet",
            binary_interfaces=False,
            compatibility=compatibility,
            selected_carriers=selected_carriers,
            selected_backbones=selected_backbones,
            failed_edge_keys=failed_edge_keys,
        )
        return self.solve_problem(problem, "fixed_recourse_total_unmet")

    def solve_graph_lp(self, scenarios: Sequence[Scenario], *, compatibility: bool) -> SolveBundle:
        # A nonbinary graph formulation admits every documented interface.
        carriers, backbones = self.available_interface_keys(scenarios)
        problem = self.build_problem(
            scenarios,
            objective="total_unmet",
            binary_interfaces=False,
            compatibility=compatibility,
            selected_carriers=carriers,
            selected_backbones=backbones,
        )
        return self.solve_problem(problem, "graph_lp_compat" if compatibility else "graph_lp_generic")

    def solve_star_lp(self, scenarios: Sequence[Scenario]) -> pd.DataFrame:
        """Port-country star LP ablation without C2 backbone topology.

        This is intentionally a capacity-only upper-bound baseline: documented
        terminal-to-backbone interface capacity may reach any facility demand
        without a transmission edge.  It is not a physical network model.
        """
        rows: list[dict[str, object]] = []
        for scenario in scenarios:
            edges = self.scenario_edges(scenario, star=True)
            sources = self.source_has_any_carrier(scenario)
            capacity = float(edges[edges["edge_id"].isin(sources)]["capacity_gwh_per_year"].sum())
            demand = self.scenario_demands(scenario)
            total = float(demand["target_gwh_per_year"].sum())
            served = min(capacity, total)
            unmet = total - served
            rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "year": scenario.year,
                    "infrastructure_level": scenario.level,
                    "demand_level": scenario.demand_level,
                    "total_demand_gwh": total,
                    "served_gwh": served,
                    "unmet_gwh": unmet,
                    "demand_cut_rate_pct": 100.0 * unmet / total if total else 0.0,
                    "method": "port_country_star_lp",
                    "note": "Topology-free upper bound; it does not claim a physical terminal-to-facility route.",
                }
            )
        return pd.DataFrame(rows)

    def extract_selection(self, solution: SolveBundle) -> tuple[set[str], set[str]]:
        x = solution.result.x
        carrier = {
            key[1]
            for key, index in solution.problem.variable_index.items()
            if key[0] == "y" and x[index] > 0.5
        }
        backbone = {
            key[1]
            for key, index in solution.problem.variable_index.items()
            if key[0] == "z" and x[index] > 0.5
        }
        return carrier, backbone

    def metrics(self, solution: SolveBundle) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Return scenario, country, flow/utilisation, and interface result tables."""
        x = solution.result.x
        var = solution.problem.variable_index
        info = solution.problem.metadata["scenarios"]
        scenario_rows: list[dict[str, object]] = []
        country_rows: list[dict[str, object]] = []
        flow_rows: list[dict[str, object]] = []
        interface_rows: list[dict[str, object]] = []
        selected_carriers, selected_backbones = self.extract_selection(solution)
        for scenario_id, scenario_info in info.items():
            demand: pd.DataFrame = scenario_info["demand"]
            edges: pd.DataFrame = scenario_info["edges"]
            total = float(scenario_info["total_demand"])
            unmet_by_facility: dict[str, float] = {}
            served_by_facility: dict[str, float] = {}
            for _, facility in demand.iterrows():
                facility_id = _text(facility["facility_id"])
                u = float(x[var[("u", scenario_id, facility_id)]])
                unmet_by_facility[facility_id] = u
                served_by_facility[facility_id] = float(facility["target_gwh_per_year"]) - u
            unmet = float(sum(unmet_by_facility.values()))
            scenario_rows.append(
                {
                    "scenario_id": scenario_id,
                    "total_demand_gwh": total,
                    "served_gwh": total - unmet,
                    "unmet_gwh": unmet,
                    "demand_cut_rate_pct": 100.0 * unmet / total if total else 0.0,
                    "selected_terminal_carrier_interfaces": len(selected_carriers),
                    "selected_terminal_backbone_interfaces": len(selected_backbones),
                    "service_cost_status": "not_reported_no_harmonised_public_terminal_service_cost_schedule",
                }
            )
            country_demand = demand.groupby("country", as_index=False)["target_gwh_per_year"].sum()
            for _, group in country_demand.iterrows():
                country = _text(group["country"])
                facility_ids = demand.loc[demand["country"].eq(country), "facility_id"].tolist()
                country_unmet = sum(unmet_by_facility[_text(fid)] for fid in facility_ids)
                country_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "country": country,
                        "demand_gwh": float(group["target_gwh_per_year"]),
                        "unmet_gwh": country_unmet,
                        "demand_cut_rate_pct": 100.0 * country_unmet / float(group["target_gwh_per_year"]),
                    }
                )
            for _, edge in edges.iterrows():
                per_carrier: dict[str, float] = {}
                for carrier in self._scenario_carriers(solution.problem.metadata["compatibility"]):
                    key = ("f", scenario_id, _text(edge["edge_id"]), carrier)
                    if key in var:
                        value = float(x[var[key]])
                        per_carrier[carrier] = value
                aggregate_flow = float(sum(per_carrier.values()))
                capacity = float(edge["capacity_gwh_per_year"])
                aggregate_utilisation = 100.0 * aggregate_flow / capacity
                for carrier, value in per_carrier.items():
                    if value > TOLERANCE:
                        flow_rows.append(
                            {
                                "scenario_id": scenario_id,
                                "edge_id": _text(edge["edge_id"]),
                                "edge_type": _text(edge["edge_type"]),
                                "from_node": _text(edge["from_node"]),
                                "to_node": _text(edge["to_node"]),
                                "carrier": carrier,
                                "flow_gwh": value,
                                "capacity_gwh": capacity,
                                "carrier_utilisation_pct": 100.0 * value / capacity,
                                "edge_total_utilisation_pct": aggregate_utilisation,
                            }
                        )
                # Emit explicit zero/positive utilisation for the N-1 edge set.
                flow_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "edge_id": _text(edge["edge_id"]),
                        "edge_type": _text(edge["edge_type"]),
                        "from_node": _text(edge["from_node"]),
                        "to_node": _text(edge["to_node"]),
                        "carrier": "__aggregate__",
                        "flow_gwh": aggregate_flow,
                        "capacity_gwh": capacity,
                        "carrier_utilisation_pct": aggregate_utilisation,
                        "edge_total_utilisation_pct": aggregate_utilisation,
                    }
                )
        for carrier_key in sorted(selected_carriers):
            terminal, carrier = carrier_key.split("|", 1)
            interface_rows.append(
                {
                    "interface_type": "terminal_carrier",
                    "interface_key": carrier_key,
                    "terminal_node": terminal,
                    "carrier": carrier,
                    "selected": True,
                    "interpretation": "Priority engineering-verification interface, not an investment decision.",
                }
            )
        for backbone_key in sorted(selected_backbones):
            terminal, backbone = backbone_key.split("|", 1)
            interface_rows.append(
                {
                    "interface_type": "terminal_backbone",
                    "interface_key": backbone_key,
                    "terminal_node": terminal,
                    "backbone_node": backbone,
                    "selected": True,
                    "interpretation": "Priority engineering-verification interface, not an investment decision.",
                }
            )
        return (
            pd.DataFrame(scenario_rows),
            pd.DataFrame(country_rows),
            pd.DataFrame(flow_rows),
            pd.DataFrame(interface_rows),
        )

    def facility_metrics(self, solution: SolveBundle) -> pd.DataFrame:
        """Return demand, service, and curtailment at every admitted facility."""
        x = solution.result.x
        var = solution.problem.variable_index
        rows: list[dict[str, object]] = []
        for scenario_id, scenario_info in solution.problem.metadata["scenarios"].items():
            for _, facility in scenario_info["demand"].iterrows():
                facility_id = _text(facility["facility_id"])
                demand = float(facility["target_gwh_per_year"])
                unmet = float(x[var[("u", scenario_id, facility_id)]])
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "facility_id": facility_id,
                        "country": _text(facility["country"]),
                        "target_gwh_per_year": demand,
                        "served_gwh_per_year": demand - unmet,
                        "unmet_gwh_per_year": unmet,
                        "demand_cut_rate_pct": 100.0 * unmet / demand if demand else 0.0,
                    }
                )
        return pd.DataFrame(rows)

    def audit_problem(self, problem: BuiltProblem) -> dict[str, Any]:
        """Expose numerical/method checks used by unit tests and manuscript audit."""
        return {
            "variables": len(problem.variable_index),
            "constraints": int(problem.constraints.A.shape[0]),
            "integer_variables": int(problem.integrality.sum()),
            "scenarios": sorted(problem.metadata["scenarios"]),
            "binary_interfaces": problem.metadata["binary_interfaces"],
            "compatibility": problem.metadata["compatibility"],
            "service_cost_rule": "No cost coefficient is included in any optimisation objective.",
            "objective_order": ["worst demand-cut rate", "total unmet demand", "interface count"],
        }

    def audit_solution(self, solution: SolveBundle) -> dict[str, Any]:
        """Numerically audit bounds, constraints, and binary decisions.

        The values are exported with each experiment so that a manuscript
        result is never separated from its feasibility checks.
        """
        x = np.asarray(solution.result.x, dtype=float)
        problem = solution.problem
        activity = np.asarray(problem.constraints.A @ x, dtype=float).reshape(-1)
        lower_violation = np.maximum(problem.constraints.lb - activity, 0.0)
        upper_violation = np.maximum(activity - problem.constraints.ub, 0.0)
        bound_violation = max(
            float(np.maximum(problem.lower - x, 0.0).max(initial=0.0)),
            float(np.maximum(x - problem.upper, 0.0).max(initial=0.0)),
        )
        integer_indices = np.flatnonzero(problem.integrality)
        integrality_deviation = (
            float(np.max(np.abs(x[integer_indices] - np.round(x[integer_indices]))))
            if len(integer_indices)
            else 0.0
        )
        return {
            **self.audit_problem(problem),
            "objective_value": float(solution.result.fun),
            "max_constraint_violation": float(max(lower_violation.max(initial=0.0), upper_violation.max(initial=0.0))),
            "max_bound_violation": bound_violation,
            "max_integrality_deviation": integrality_deviation,
            "solver_status": int(solution.result.status),
            "solver_message": str(solution.result.message),
        }


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
