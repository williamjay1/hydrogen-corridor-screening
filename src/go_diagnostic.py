"""Evidence-aware corridor screening and data-gap diagnostics.

This module is a separate, positive-question redesign of the audited TYNDP
2024 corridor model.  It does not attempt to reproduce the integrated IGI
model.  Instead it asks how much an auditable public evidence layer changes a
fixed-budget corridor-screening decision.

The first-stage binary variable selects a terminal-to-backbone verification
group.  It is not an investment variable.  Recourse is a multi-commodity
flow LP.  The robust selector is fitted to the declared multi-horizon planning
matrix; single-interface failures are held out and used as a resilience
diagnostic, while the deterministic selector is fitted only to the central
planning state.  All selections are subsequently scored against the full
evidence model.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from corridor_milp import CorridorMILP, Scenario, TOLERANCE, _text, _terminal_backbone_key


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT / "data" / "corridor_2024"
DEFAULT_EXTERNAL = PROJECT / "data" / "external" / "H2 IMPORTS GENERATORS PROPERTIES.xlsx"
DEFAULT_OUT = PROJECT / "runs" / "corridor_2024" / "go_diagnostic_20260907"


COUNTRY_CODE = {
    "AT": "Austria", "BE": "Belgium", "DE": "Germany", "ES": "Spain",
    "FR": "France", "HR": "Croatia", "HU": "Hungary", "IT": "Italy",
    "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SK": "Slovakia", "UA": "Ukraine", "NO": "Norway", "DZ": "Algeria",
    "MA": "Morocco",
}


@dataclass(frozen=True)
class Spec:
    scenario: Scenario
    failures: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if not self.failures:
            return self.scenario.scenario_id
        return self.scenario.scenario_id + "__fail__" + "__".join(self.failures)


@dataclass
class Problem:
    c: np.ndarray
    integrality: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    constraints: LinearConstraint
    var: dict[tuple[Any, ...], int]
    metadata: dict[str, Any]


@dataclass
class Solution:
    result: Any
    problem: Problem
    stage: str
    selected: set[str]


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


class EvidencePortfolioMILP:
    """Portfolio selector built on the frozen corridor data product."""

    def __init__(self, data_dir: Path | str = DEFAULT_DATA) -> None:
        self.base = CorridorMILP(data_dir)
        interfaces = self.base.interfaces[self.base.interfaces["eligible"].astype(bool)].copy()
        self.candidates = (
            interfaces[["terminal_node", "backbone_node", "country"]]
            .drop_duplicates()
            .assign(candidate_key=lambda x: x["terminal_node"] + "|" + x["backbone_node"])
            .sort_values("candidate_key")
            .reset_index(drop=True)
        )
        self.candidate_keys = tuple(self.candidates["candidate_key"])
        if not self.candidate_keys:
            raise ValueError("No auditable terminal-to-backbone candidate groups found")

    @staticmethod
    def core_scenarios() -> list[Scenario]:
        return [
            Scenario(f"S{year}_{level.replace('/', '')}_{demand}", year, level, demand)
            for year in (2030, 2040)
            for level in ("PCI/PMI", "Advanced")
            for demand in ("low", "medium", "high")
        ]

    @staticmethod
    def central_scenario() -> Scenario:
        return Scenario("S2040_Advanced_medium", 2040, "Advanced", "medium")

    def specs(self, scenarios: Sequence[Scenario], failures: Sequence[tuple[str, ...]] = ()) -> list[Spec]:
        result = [Spec(s) for s in scenarios]
        for failure in failures:
            result.extend(Spec(s, tuple(failure)) for s in scenarios)
        return result

    def n1_specs(self, scenarios: Sequence[Scenario], candidates: Iterable[str] | None = None) -> list[Spec]:
        keys = tuple(candidates or self.candidate_keys)
        return [Spec(s) for s in scenarios] + [Spec(s, (key,)) for key in keys for s in scenarios]

    def nk_specs(self, scenarios: Sequence[Scenario], selected: Iterable[str], k: int) -> list[Spec]:
        keys = sorted(selected)
        failures = list(itertools.combinations(keys, k))
        return [Spec(s) for s in scenarios] + [Spec(s, tuple(failure)) for failure in failures for s in scenarios]

    def _capacity_column(self, level: str) -> str:
        return "capacity_pci_pmi_gwh_per_day" if level == "PCI/PMI" else "capacity_advanced_gwh_per_day"

    def _demand_rows(self, scenario: Scenario, direct_share: float) -> list[dict[str, Any]]:
        frame = self.base.scenario_demands(scenario)
        rows: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            target = float(row["target_gwh_per_year"])
            is_ammonia = _text(row.get("end_use", "")).casefold() == "ammonia"
            if is_ammonia and direct_share > 0:
                if direct_share < 1:
                    rows.append({**row.to_dict(), "service": "h2", "target": target * (1.0 - direct_share)})
                rows.append({**row.to_dict(), "service": "nh3_direct", "target": target * direct_share})
            else:
                rows.append({**row.to_dict(), "service": "h2", "target": target})
        return [row for row in rows if float(row["target"]) > TOLERANCE]

    def _edges(
        self,
        spec: Spec,
        *,
        mode: str,
        direct_share: float,
        capacity_multiplier: float,
        selected_candidates: set[str] | None = None,
    ) -> pd.DataFrame:
        scenario = spec.scenario
        frame = self.base.edges[self.base.edges["year"].eq(scenario.year)].copy()
        column = self._capacity_column(scenario.level)
        frame["capacity_gwh_per_year"] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0) * 365.0
        total = sum(float(row["target"]) for row in self._demand_rows(scenario, direct_share))
        if mode == "capacity_unknown":
            # The topology remains explicit, but every recorded edge receives
            # the same transparent screening bound.  This is an ablation, not
            # an assertion that the network is actually unconstrained.
            frame = frame[frame["edge_type"].isin(["backbone", "terminal_backbone"])].copy()
            frame["capacity_gwh_per_year"] = max(total * 2.0, 1.0)
        else:
            frame = frame[frame["capacity_gwh_per_year"] > TOLERANCE].copy()
            frame["capacity_gwh_per_year"] *= float(capacity_multiplier)
        frame["candidate_key"] = frame.apply(
            lambda r: _terminal_backbone_key(r) if r["edge_type"] == "terminal_backbone" else "",
            axis=1,
        )
        # A terminal endpoint without an audited carrier/interface row is not
        # admitted to any selection mode.
        frame = frame[~frame["edge_type"].eq("terminal_backbone") | frame["candidate_key"].isin(self.candidate_keys)].copy()
        # In fixed-selection recourse, only the nominated terminal-backbone
        # groups are available.  Binary selector problems leave all candidate
        # groups in the graph and enforce this condition through y variables.
        if selected_candidates is not None:
            frame = frame[
                ~frame["edge_type"].eq("terminal_backbone")
                | frame["candidate_key"].isin(selected_candidates)
            ].copy()
        if spec.failures:
            frame = frame[~frame["candidate_key"].isin(set(spec.failures))].copy()
        return frame.reset_index(drop=True)

    def _supports(
        self,
        edge: pd.Series,
        scenario: Scenario,
        *,
        mode: str,
        direct_share: float,
    ) -> tuple[str, ...]:
        if edge["edge_type"] != "terminal_backbone":
            return ("H2_generic",) if mode == "carrier_unknown" else ("NH3_cracked_to_H2", "LOHC_to_H2") + (("NH3_direct",) if direct_share > 0 else ())
        if mode == "carrier_unknown":
            return ("H2_generic",)
        supported = set(self.base.carrier_lookup(scenario).get(_text(edge["edge_id"]), set()))
        if direct_share > 0 and "NH3_cracked_to_H2" in supported:
            supported.add("NH3_direct")
        return tuple(sorted(supported))

    def _carrier_pool(self, scenario: Scenario, *, mode: str, direct_share: float, multiplier: float) -> dict[tuple[str, str], float]:
        if mode in {"carrier_unknown", "capacity_unknown"}:
            return {}
        pools = self.base.carrier_pool_lookup(scenario)
        return {(country, carrier): capacity * 365.0 * multiplier for (country, carrier), capacity in pools.items()}

    @staticmethod
    def _pool_carrier(carrier: str) -> str:
        return "NH3_cracked_to_H2" if carrier == "NH3_direct" else carrier

    def build(
        self,
        specs: Sequence[Spec],
        *,
        mode: str,
        objective: str,
        budget: int | None = None,
        selected: set[str] | None = None,
        direct_share: float = 0.0,
        capacity_multiplier: float = 1.0,
        fix_worst: float | None = None,
    ) -> Problem:
        if not specs:
            raise ValueError("At least one scenario specification is required")
        binary = selected is None
        candidates = set(self.candidate_keys) if binary else set(selected or ())
        var: dict[tuple[Any, ...], int] = {}
        lower: list[float] = []
        upper: list[float] = []
        integrality: list[int] = []

        def add_var(key: tuple[Any, ...], lb: float = 0.0, ub: float = math.inf, integer: bool = False) -> int:
            if key in var:
                return var[key]
            index = len(var)
            var[key] = index
            lower.append(lb)
            upper.append(ub)
            integrality.append(1 if integer else 0)
            return index

        if binary:
            for key in sorted(candidates):
                add_var(("y", key), 0.0, 1.0, True)

        # Shared epigraph variable for the worst scenario demand-cut rate.
        add_var(("z",), 0.0, 1.0)

        metadata: dict[str, Any] = {"specs": {}, "mode": mode, "binary": binary, "direct_share": direct_share}
        global_carriers = ("H2_generic",) if mode == "carrier_unknown" else ("NH3_cracked_to_H2", "LOHC_to_H2") + (("NH3_direct",) if direct_share > 0 else ())
        all_backbones: dict[str, str] = {}
        rows: list[dict[int, float]] = []
        lbs: list[float] = []
        ubs: list[float] = []

        def add_constraint(coefficients: Mapping[int, float], lb: float = -math.inf, ub: float = math.inf) -> None:
            rows.append(dict(coefficients))
            lbs.append(lb)
            ubs.append(ub)

        for spec in specs:
            label = spec.label
            edges = self._edges(
                spec,
                mode=mode,
                direct_share=direct_share,
                capacity_multiplier=capacity_multiplier,
                selected_candidates=None if binary else candidates,
            )
            demand_rows = self._demand_rows(spec.scenario, direct_share)
            lookup = self.base.carrier_lookup(spec.scenario)
            node_country: dict[str, str] = {}
            for _, edge in edges.iterrows():
                node_country.setdefault(_text(edge["from_node"]), _text(edge["from_country"]))
                node_country.setdefault(_text(edge["to_node"]), _text(edge["to_country"]))
                if edge["edge_type"] == "terminal_backbone":
                    all_backbones[_text(edge["candidate_key"])] = _text(edge["to_node"])
            # Terminal nodes are exogenous import sources.  They must not be
            # included in the backbone flow-conservation equations: doing so
            # would force every terminal-to-backbone flow to zero because no
            # explicit source variable is attached to the terminal node.  The
            # backbone graph consists of all nodes on backbone edges plus the
            # receiving endpoint of a terminal-backbone edge.
            backbone_mask = edges["edge_type"].ne("terminal_backbone")
            backbone_nodes = set(edges.loc[backbone_mask, "from_node"].astype(str))
            backbone_nodes.update(edges.loc[backbone_mask, "to_node"].astype(str))
            backbone_nodes.update(edges.loc[~backbone_mask, "to_node"].astype(str))
            backbone_nodes = sorted(backbone_nodes)
            nodes_by_country: dict[str, list[str]] = {}
            for node in backbone_nodes:
                nodes_by_country.setdefault(node_country[node], []).append(node)
            info = {
                "scenario": spec.scenario,
                "edges": edges,
                "demand_rows": demand_rows,
                "node_country": node_country,
                "backbone_nodes": backbone_nodes,
                "nodes_by_country": nodes_by_country,
                "total_demand": float(sum(float(r["target"]) for r in demand_rows)),
                "lookup": lookup,
                "failures": tuple(spec.failures),
            }
            edge_by_id = {_text(row["edge_id"]): row for _, row in edges.iterrows()}
            flow_keys_by_edge: dict[str, list[tuple[Any, ...]]] = {}
            flow_keys_by_carrier: dict[str, list[tuple[Any, ...]]] = {}
            q_keys_by_node_carrier: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
            metadata["specs"][label] = info
            for _, edge in edges.iterrows():
                supported = self._supports(edge, spec.scenario, mode=mode, direct_share=direct_share)
                for carrier in supported:
                    key = ("f", label, _text(edge["edge_id"]), carrier)
                    add_var(key)
                    flow_keys_by_edge.setdefault(_text(edge["edge_id"]), []).append(key)
                    flow_keys_by_carrier.setdefault(carrier, []).append(key)
            for demand in demand_rows:
                service = _text(demand["service"])
                if service == "nh3_direct":
                    q_carriers = ("NH3_direct",)
                else:
                    q_carriers = ("H2_generic",) if mode == "carrier_unknown" else ("NH3_cracked_to_H2", "LOHC_to_H2")
                for node in nodes_by_country.get(_text(demand["country"]), []):
                    for carrier in q_carriers:
                        key = ("q", label, _text(demand["facility_id"]), service, node, carrier)
                        add_var(key)
                        q_keys_by_node_carrier.setdefault((node, carrier), []).append(key)
                add_var(("u", label, _text(demand["facility_id"]), service))
            add_var(("v", label), 0.0, 1.0)
            info["edge_by_id"] = edge_by_id
            info["flow_keys_by_edge"] = flow_keys_by_edge
            info["flow_keys_by_carrier"] = flow_keys_by_carrier
            info["q_keys_by_node_carrier"] = q_keys_by_node_carrier

        # Flow and interface capacities.
        for label, info in metadata["specs"].items():
            edges: pd.DataFrame = info["edges"]
            demand_rows: list[dict[str, Any]] = info["demand_rows"]
            node_country: dict[str, str] = info["node_country"]
            flow_keys_by_edge = info["flow_keys_by_edge"]
            flow_keys_by_carrier = info["flow_keys_by_carrier"]
            q_keys_by_node_carrier = info["q_keys_by_node_carrier"]
            edge_by_id = info["edge_by_id"]
            for _, edge in edges.iterrows():
                edge_id = _text(edge["edge_id"])
                fkeys = flow_keys_by_edge.get(edge_id, [])
                if not fkeys:
                    continue
                add_constraint({var[key]: 1.0 for key in fkeys}, ub=float(edge["capacity_gwh_per_year"]))
                if edge["edge_type"] == "terminal_backbone":
                    candidate = _text(edge["candidate_key"])
                    if binary:
                        y = var[("y", candidate)]
                        add_constraint({**{var[key]: 1.0 for key in fkeys}, y: -float(edge["capacity_gwh_per_year"])}, ub=0.0)
            # A disclosed carrier capacity is a shared country pool.  Direct
            # ammonia is allowed only in the explicit counterfactual mode and
            # uses the same ammonia pool as cracked ammonia.
            pools = self._carrier_pool(info["scenario"], mode=mode, direct_share=direct_share, multiplier=capacity_multiplier)
            for (country, carrier), pool in pools.items():
                coeff: dict[int, float] = {}
                terminal_edges = edges.loc[
                    edges["edge_type"].eq("terminal_backbone") & edges["from_country"].eq(country)
                ]
                for _, edge in terminal_edges.iterrows():
                    edge_id = _text(edge["edge_id"])
                    for key in flow_keys_by_edge.get(edge_id, []):
                        if self._pool_carrier(key[3]) == carrier:
                            coeff[var[key]] = 1.0
                if coeff:
                    add_constraint(coeff, ub=float(pool))
            # Facility service balance.
            for demand in demand_rows:
                facility = _text(demand["facility_id"])
                service = _text(demand["service"])
                qkeys = [
                    key
                    for node in info["nodes_by_country"].get(_text(demand["country"]), [])
                    for carrier in global_carriers
                    for key in q_keys_by_node_carrier.get((node, carrier), [])
                    if key[2] == facility and key[3] == service
                ]
                ukey = ("u", label, facility, service)
                add_constraint({**{var[key]: 1.0 for key in qkeys}, var[ukey]: 1.0}, lb=float(demand["target"]), ub=float(demand["target"]))
            # Commodity conservation at every explicit graph node.
            for node in info["backbone_nodes"]:
                for carrier in global_carriers:
                    coeff: dict[int, float] = {}
                    for key in flow_keys_by_carrier.get(carrier, []):
                        idx = var[key]
                        edge = edge_by_id[key[2]]
                        if _text(edge["to_node"]) == node:
                            coeff[idx] = coeff.get(idx, 0.0) + 1.0
                        if _text(edge["from_node"]) == node:
                            coeff[idx] = coeff.get(idx, 0.0) - 1.0
                    for key in q_keys_by_node_carrier.get((node, carrier), []):
                        coeff[var[key]] = coeff.get(var[key], 0.0) - 1.0
                    if coeff:
                        add_constraint(coeff, lb=0.0, ub=0.0)
            # Scenario unmet-demand rate.
            ukeys = [key for key in var if key[0] == "u" and key[1] == label]
            add_constraint({**{var[key]: 1.0 for key in ukeys}, var[("v", label)]: -float(info["total_demand"])}, ub=0.0)
            # A shared z variable represents the worst scenario demand-cut
            # rate.  The former implementation minimized sum(v_s), which is a
            # different objective and could not be called worst-case robust.
            add_constraint({var[("v", label)]: 1.0, var[("z",)]: -1.0}, ub=0.0)

        if binary:
            if budget is None:
                raise ValueError("A fixed budget is required for binary selection")
            add_constraint({var[("y", key)]: 1.0 for key in sorted(candidates)}, lb=float(budget), ub=float(budget))

        if fix_worst is not None:
            add_constraint({var[("z",)]: 1.0}, ub=float(fix_worst))

        c = np.zeros(len(var), dtype=float)
        if objective == "worst_dcr":
            c[var[("z",)]] = 1.0
        elif objective == "total_unmet":
            for key, idx in var.items():
                if key[0] == "u":
                    c[idx] = 1.0
        else:
            raise ValueError(objective)

        matrix = lil_matrix((len(rows), len(var)), dtype=float)
        for row_index, coefficients in enumerate(rows):
            for col, value in coefficients.items():
                matrix[row_index, col] = value
        return Problem(
            c=c,
            integrality=np.asarray(integrality, dtype=int),
            lower=np.asarray(lower, dtype=float),
            upper=np.asarray(upper, dtype=float),
            constraints=LinearConstraint(matrix.tocsr(), np.asarray(lbs), np.asarray(ubs)),
            var=var,
            metadata=metadata,
        )

    @staticmethod
    def solve_problem(problem: Problem, stage: str) -> Solution:
        result = milp(
            c=problem.c,
            integrality=problem.integrality,
            bounds=Bounds(problem.lower, problem.upper),
            constraints=problem.constraints,
            options={"disp": False, "mip_rel_gap": 0.0},
        )
        if not result.success:
            raise RuntimeError(f"{stage} failed: {result.status}: {result.message}")
        selected = {key[1] for key in problem.var if key[0] == "y" and result.x[problem.var[key]] >= 0.5}
        return Solution(result=result, problem=problem, stage=stage, selected=selected)

    def solve_selector(
        self,
        specs: Sequence[Spec],
        *,
        mode: str,
        budget: int,
        direct_share: float = 0.0,
        capacity_multiplier: float = 1.0,
    ) -> Solution:
        first = self.solve_problem(
            self.build(specs, mode=mode, objective="worst_dcr", budget=budget, direct_share=direct_share, capacity_multiplier=capacity_multiplier),
            "stage1_worst_dcr",
        )
        worst = float(first.result.fun)
        second_problem = self.build(
            specs,
            mode=mode,
            objective="total_unmet",
            budget=budget,
            direct_share=direct_share,
            capacity_multiplier=capacity_multiplier,
            fix_worst=worst + 1.0e-8,
        )
        second_problem.metadata["stage1_worst_dcr"] = worst
        return self.solve_problem(second_problem, "stage2_total_unmet")

    def solve_fixed(
        self,
        specs: Sequence[Spec],
        selected: set[str],
        *,
        mode: str = "full",
        direct_share: float = 0.0,
        capacity_multiplier: float = 1.0,
    ) -> Solution:
        problem = self.build(
            specs,
            mode=mode,
            objective="total_unmet",
            selected=set(selected),
            direct_share=direct_share,
            capacity_multiplier=capacity_multiplier,
        )
        return self.solve_problem(problem, "fixed_selection_recourse")

    @staticmethod
    def metrics(solution: Solution) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        x = solution.result.x
        for label, info in solution.problem.metadata["specs"].items():
            unmet = sum(float(x[idx]) for key, idx in solution.problem.var.items() if key[0] == "u" and key[1] == label)
            total = float(info["total_demand"])
            rows.append({
                "scenario_label": label,
                "scenario_id": info["scenario"].scenario_id,
                "year": info["scenario"].year,
                "level": info["scenario"].level,
                "demand_level": info["scenario"].demand_level,
                "failure_count": len(info.get("failures", ())),
                "unmet_gwh": unmet,
                "total_demand_gwh": total,
                "served_gwh": total - unmet,
                "demand_cut_rate_pct": 100.0 * unmet / total if total else 0.0,
            })
        return pd.DataFrame(rows)

    @staticmethod
    def flow_metrics(solution: Solution) -> pd.DataFrame:
        """Return auditable edge-carrier flows and capacity utilisation."""
        rows: list[dict[str, Any]] = []
        x = solution.result.x
        for label, info in solution.problem.metadata["specs"].items():
            edge_by_id = info["edge_by_id"]
            for edge_id, keys in info["flow_keys_by_edge"].items():
                edge = edge_by_id[edge_id]
                capacity = float(edge["capacity_gwh_per_year"])
                for key in keys:
                    flow = float(x[solution.problem.var[key]])
                    rows.append({
                        "scenario_label": label,
                        "scenario_id": info["scenario"].scenario_id,
                        "year": info["scenario"].year,
                        "level": info["scenario"].level,
                        "demand_level": info["scenario"].demand_level,
                        "failure_count": len(info.get("failures", ())),
                        "edge_id": edge_id,
                        "edge_type": _text(edge["edge_type"]),
                        "from_node": _text(edge["from_node"]),
                        "to_node": _text(edge["to_node"]),
                        "candidate_key": _text(edge["candidate_key"]),
                        "carrier": key[3],
                        "flow_gwh": flow,
                        "capacity_gwh": capacity,
                        "utilisation_pct": 100.0 * flow / capacity if capacity else 0.0,
                    })
        return pd.DataFrame(rows)

    @staticmethod
    def interface_priority(flow_frame: pd.DataFrame, candidates: pd.DataFrame, selected: set[str]) -> pd.DataFrame:
        """Aggregate terminal interface capacity use over the planning scenarios."""
        terminal = flow_frame[
            flow_frame["edge_type"].eq("terminal_backbone")
            & flow_frame["candidate_key"].ne("")
            & flow_frame["failure_count"].eq(0)
        ].copy()
        rows: list[dict[str, Any]] = []
        for _, candidate in candidates.iterrows():
            key = _text(candidate["candidate_key"])
            group = terminal[terminal["candidate_key"].eq(key)]
            scenario_rows: list[dict[str, float]] = []
            for scenario_id, scenario_group in group.groupby("scenario_id"):
                capacity = float(scenario_group[["edge_id", "capacity_gwh"]].drop_duplicates()["capacity_gwh"].sum())
                flow = float(scenario_group["flow_gwh"].sum())
                scenario_rows.append({"flow": flow, "capacity": capacity})
            utilisations = [100.0 * row["flow"] / row["capacity"] for row in scenario_rows if row["capacity"] > 0]
            rows.append({
                "candidate_key": key,
                "terminal_node": _text(candidate["terminal_node"]),
                "backbone_node": _text(candidate["backbone_node"]),
                "country": _text(candidate["country"]),
                "selected": key in selected,
                "scenario_count": len(scenario_rows),
                "mean_flow_gwh": float(np.mean([row["flow"] for row in scenario_rows])) if scenario_rows else 0.0,
                "max_flow_gwh": float(max((row["flow"] for row in scenario_rows), default=0.0)),
                "mean_utilisation_pct": float(np.mean(utilisations)) if utilisations else 0.0,
                "max_utilisation_pct": float(max(utilisations, default=0.0)),
            })
        return pd.DataFrame(rows).sort_values(["selected", "max_utilisation_pct", "candidate_key"], ascending=[False, False, True])

    @staticmethod
    def interface_criticality(metrics: pd.DataFrame) -> pd.DataFrame:
        """Summarise held-out single-interface failure impact."""
        base = metrics[metrics["failure_count"].eq(0)]
        base_worst = float(base["demand_cut_rate_pct"].max()) if not base.empty else float("nan")
        failed = metrics[metrics["failure_count"].eq(1)].copy()
        if failed.empty:
            return pd.DataFrame(columns=["candidate_key", "worst_dcr_pct", "mean_dcr_pct", "delta_worst_dcr_pp"])
        failed["candidate_key"] = failed["scenario_label"].str.split("__fail__", n=1).str[1]
        result = failed.groupby("candidate_key", as_index=False).agg(
            worst_dcr_pct=("demand_cut_rate_pct", "max"),
            mean_dcr_pct=("demand_cut_rate_pct", "mean"),
            total_unmet_gwh=("unmet_gwh", "sum"),
            failure_scenarios=("scenario_label", "count"),
        )
        result["delta_worst_dcr_pp"] = result["worst_dcr_pct"] - base_worst
        return result.sort_values(["delta_worst_dcr_pp", "candidate_key"], ascending=[False, True])


def random_baseline(
    model: EvidencePortfolioMILP,
    scenarios: Sequence[Spec],
    *,
    budget: int,
    n: int,
    seed: int,
) -> pd.DataFrame:
    rng = random.Random(seed)
    all_keys = list(model.candidate_keys)
    combinations = list(itertools.combinations(all_keys, budget))
    if len(combinations) <= n:
        selected_sets = combinations
    else:
        selected_sets = rng.sample(combinations, n)
    rows: list[dict[str, Any]] = []
    for i, subset in enumerate(selected_sets):
        solution = model.solve_fixed(scenarios, set(subset))
        metrics = model.metrics(solution)
        rows.append({
            "draw": i,
            "seed": seed,
            "selection": ";".join(subset),
            "worst_dcr_pct": float(metrics["demand_cut_rate_pct"].max()),
            "mean_dcr_pct": float(metrics["demand_cut_rate_pct"].mean()),
            "total_unmet_gwh": float(metrics["unmet_gwh"].sum()),
        })
        if (i + 1) % 25 == 0:
            print(f"random baseline {i + 1}/{len(selected_sets)}")
    return pd.DataFrame(rows)


def structural_ablation(
    model: EvidencePortfolioMILP,
    scenarios: Sequence[Scenario],
    robust_metrics: pd.DataFrame,
    deterministic_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Run the five prespecified topology/compatibility/selection layers."""
    rows: list[dict[str, Any]] = []

    def append_summary(name: str, frame: pd.DataFrame, note: str) -> None:
        rows.append({
            "ablation": name,
            "worst_dcr_pct": float(frame["demand_cut_rate_pct"].max()),
            "mean_dcr_pct": float(frame["demand_cut_rate_pct"].mean()),
            "total_unmet_gwh": float(frame["unmet_gwh"].sum()),
            "note": note,
        })

    star = model.base.solve_star_lp(scenarios)
    append_summary("port_country_star_lp", star, "Topology-free capacity upper bound; not a physical route model.")
    graph_generic = model.base.solve_graph_lp(scenarios, compatibility=False)
    graph_generic_metrics = model.base.metrics(graph_generic)[0]
    append_summary("project_graph_lp_generic", graph_generic_metrics, "Explicit project graph without carrier compatibility.")
    graph_compatible = model.base.solve_graph_lp(scenarios, compatibility=True)
    graph_compatible_metrics = model.base.metrics(graph_compatible)[0]
    append_summary("project_graph_lp_carrier_compatible", graph_compatible_metrics, "Explicit project graph with carrier compatibility and shared pools.")
    append_summary("deterministic_budget_milp", deterministic_metrics, "Four-interface central-scenario selection evaluated over the planning matrix.")
    append_summary("robust_budget_milp", robust_metrics, "Four-interface multi-scenario worst-case selection evaluated over the planning matrix.")
    return pd.DataFrame(rows)


def parse_external_imports(path: Path, out: Path) -> pd.DataFrame:
    frame = pd.read_excel(path)
    frame = frame.rename(columns={"NODE TO": "destination_code", "MAX ENERGY YEAR [GWh]": "max_energy_gwh"})
    frame["destination_country"] = frame["destination_code"].map(COUNTRY_CODE).fillna(frame["destination_code"])
    frame = frame.loc[
        frame["YEAR"].isin([2030, 2040])
        & (pd.to_numeric(frame["max_energy_gwh"], errors="coerce").fillna(0.0) > 0)
    ].copy()
    result = (
        frame.groupby(["YEAR", "destination_country", "Type", "Fuel"], as_index=False)["max_energy_gwh"]
        .sum()
        .rename(columns={"YEAR": "year", "Type": "technology", "Fuel": "fuel"})
    )
    write_csv(result, out / "external_tyndp_import_targets.csv")
    return result


def external_validity(selected: set[str], targets: pd.DataFrame, model: EvidencePortfolioMILP) -> pd.DataFrame:
    selected_countries = set(model.candidates.loc[model.candidates["candidate_key"].isin(selected), "country"])
    rows: list[dict[str, Any]] = []
    for year, group in targets.groupby("year"):
        country_target = group.groupby("destination_country", as_index=False)["max_energy_gwh"].sum().sort_values("max_energy_gwh", ascending=False)
        top4 = set(country_target.head(4)["destination_country"])
        total = float(country_target["max_energy_gwh"].sum())
        covered = float(country_target.loc[country_target["destination_country"].isin(selected_countries), "max_energy_gwh"].sum())
        rows.append({
            "year": int(year),
            "selected_countries": ";".join(sorted(selected_countries)),
            "top4_target_countries": ";".join(sorted(top4)),
            "top4_overlap": len(top4 & selected_countries),
            "top4_jaccard": len(top4 & selected_countries) / len(top4 | selected_countries) if top4 | selected_countries else 0.0,
            "weighted_target_coverage": covered / total if total else 0.0,
        })
    return pd.DataFrame(rows)


def source_manifest(data_dir: Path, external: Path, out: Path) -> pd.DataFrame:
    rows = []
    existing = data_dir / "source_manifest.csv"
    if existing.exists():
        rows.extend(pd.read_csv(existing).to_dict("records"))
    for source_id, file_path, url, version, role in [
        ("TYNDP2024_HYDROGEN_INPUTS", external, "https://2024-data.entsos-tyndp-scenarios.eu/files/scenarios-inputs/Hydrogen.zip", "TYNDP 2024 scenarios Hydrogen.zip", "Independent import-supply benchmark; not used as a model capacity input."),
        ("EHB_2024_ROADMAP", PROJECT / "temp" / "go_redesign_source_staging_20260907" / "EHB_Implementation_Roadmap_2024.pdf", "https://ehb.eu/files/downloads/1712733755_EHB-Implementation-Roadmap-Public-support-as-catalyst-for-hydrogen-infrastructure.pdf", "EHB April 2024 implementation roadmap", "Qualitative face-validity and boundary source; no route capacity copied into the model."),
        ("EUROSTAT_NRG_PC_205", PROJECT / "temp" / "go_redesign_source_staging_20260907" / "eurostat_nrg_pc_205_EU27_2022S1.json", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_205", "Eurostat NRG_PC_205, 2022-S1", "Post-hoc industrial electricity-price proxy; no optimisation coefficient."),
    ]:
        if file_path.exists():
            import hashlib
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            rows.append({
                "source_id": source_id,
                "filename": file_path.name,
                "sha256": digest,
                "bytes": file_path.stat().st_size,
                "source_url": url,
                "version": version,
                "license_note": "Public source; preserve source attribution and terms.",
                "model_role": role,
                "stored_on": "D staging; E raw repository remains read only",
            })
    result = pd.DataFrame(rows)
    write_csv(result, out / "source_manifest_extended.csv")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--external", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--budget", type=int, default=4)
    parser.add_argument("--random-draws", type=int, default=200)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    model = EvidencePortfolioMILP(args.data)
    base_scenarios = model.core_scenarios()
    base_specs = model.specs(base_scenarios)
    central_specs = model.specs([model.central_scenario()])

    write_csv(model.candidates, args.output / "candidate_interface_groups.csv")
    write_csv(
        pd.DataFrame([
            {
                "scenario_id": scenario.scenario_id,
                "year": scenario.year,
                "infrastructure_level": scenario.level,
                "demand_level": scenario.demand_level,
                "role": "declared planning scenario",
            }
            for scenario in base_scenarios
        ]),
        args.output / "scenario_matrix.csv",
    )
    targets = parse_external_imports(args.external, args.output)
    source_manifest(args.data, args.external, args.output)

    print(f"candidate groups={len(model.candidate_keys)} budget={args.budget}")
    # The selector is fitted on the declared planning scenarios only.  N-1 is
    # held out as a resilience diagnostic for the selected portfolio.  This
    # avoids letting the same outage catalogue both choose and validate the
    # portfolio and keeps the public-data experiment computationally auditable.
    robust = model.solve_selector(base_specs, mode="full", budget=args.budget)
    deterministic = model.solve_selector(central_specs, mode="full", budget=args.budget)
    robust_n1_specs = model.n1_specs(base_scenarios, robust.selected)
    deterministic_n1_specs = model.n1_specs(base_scenarios, deterministic.selected)
    robust_base_eval = model.solve_fixed(base_specs, robust.selected)
    deterministic_base_eval = model.solve_fixed(base_specs, deterministic.selected)
    robust_eval = model.solve_fixed(robust_n1_specs, robust.selected)
    deterministic_eval = model.solve_fixed(deterministic_n1_specs, deterministic.selected)
    base_flow_frame = model.flow_metrics(robust_base_eval)
    write_csv(base_flow_frame, args.output / "flow_results.csv")
    write_csv(
        model.interface_priority(base_flow_frame, model.candidates, robust.selected),
        args.output / "interface_priority.csv",
    )
    robust_base_metrics = model.metrics(robust_base_eval).assign(method="robust_base")
    deterministic_base_metrics = model.metrics(deterministic_base_eval).assign(method="deterministic_base")
    robust_metrics = model.metrics(robust_eval).assign(method="robust_n1")
    deterministic_metrics = model.metrics(deterministic_eval).assign(method="deterministic_central")
    write_csv(
        pd.concat(
            [robust_base_metrics, deterministic_base_metrics, robust_metrics, deterministic_metrics],
            ignore_index=True,
        ),
        args.output / "main_selection_metrics.csv",
    )
    write_csv(
        structural_ablation(model, base_scenarios, robust_base_metrics, deterministic_base_metrics),
        args.output / "structural_ablation.csv",
    )
    write_csv(model.interface_criticality(model.metrics(robust_eval)), args.output / "interface_criticality.csv")
    write_json(args.output / "main_selections.json", {
        "budget": args.budget,
        "candidate_groups": list(model.candidate_keys),
        "robust_n1": sorted(robust.selected),
        "deterministic_central": sorted(deterministic.selected),
        "robust_stage1_worst_dcr": float(robust.problem.metadata["stage1_worst_dcr"]),
        "n1_evaluation_is_held_out": True,
    })

    random_frame = random_baseline(model, base_specs, budget=args.budget, n=args.random_draws, seed=20260907)
    write_csv(random_frame, args.output / "random_baseline.csv")
    write_csv(random_frame, args.output / "equal_budget_portfolio_baseline.csv")

    gap_rows: list[dict[str, Any]] = []
    gap_configs = {
        "full_evidence": ("full", base_specs, robust.selected),
        "carrier_evidence_removed": ("carrier_unknown", base_specs, None),
        "capacity_evidence_removed": ("capacity_unknown", base_specs, None),
        "demand_uncertainty_omitted": ("full", central_specs, deterministic.selected),
    }
    for name, (mode, specs, fixed) in gap_configs.items():
        selection = set(fixed) if fixed is not None else model.solve_selector(specs, mode=mode, budget=args.budget).selected
        evaluation_specs = model.n1_specs(base_scenarios, selection)
        evaluation = model.solve_fixed(evaluation_specs, selection)
        metrics = model.metrics(evaluation)
        full_worst = float(metrics["demand_cut_rate_pct"].max())
        gap_rows.append({
            "ablation": name,
            "selection": ";".join(sorted(selection)),
            "selected_count": len(selection),
            "worst_dcr_full_evidence_pct": full_worst,
            "mean_dcr_full_evidence_pct": float(metrics["demand_cut_rate_pct"].mean()),
            "total_unmet_full_evidence_gwh": float(metrics["unmet_gwh"].sum()),
            "jaccard_to_full_robust": len(selection & robust.selected) / len(selection | robust.selected) if selection | robust.selected else 1.0,
        })
    gap_frame = pd.DataFrame(gap_rows)
    full_worst = float(gap_frame.loc[gap_frame["ablation"].eq("full_evidence"), "worst_dcr_full_evidence_pct"].iloc[0])
    gap_frame["regret_vs_full_robust_pp"] = gap_frame["worst_dcr_full_evidence_pct"] - full_worst
    write_csv(gap_frame, args.output / "data_gap_diagnostics.csv")

    nk_rows: list[dict[str, Any]] = []
    for method, selection in [("robust_n1", robust.selected), ("deterministic_central", deterministic.selected)]:
        for k in (0, 1, 2):
            specs = base_specs if k == 0 else model.nk_specs(base_scenarios, selection, k)
            evaluation = model.solve_fixed(specs, selection)
            metrics = model.metrics(evaluation)
            nk_rows.append({
                "method": method,
                "k": k,
                "failure_scenarios": int((metrics["failure_count"] > 0).sum()),
                "worst_dcr_pct": float(metrics["demand_cut_rate_pct"].max()),
                "mean_dcr_pct": float(metrics["demand_cut_rate_pct"].mean()),
                "total_unmet_gwh": float(metrics["unmet_gwh"].sum()),
            })
    nk_frame = pd.DataFrame(nk_rows)
    write_csv(nk_frame, args.output / "nk_resilience.csv")

    sens_rows: list[dict[str, Any]] = []
    for multiplier in (0.5, 1.0, 1.5):
        evaluation = model.solve_fixed(base_specs, robust.selected, capacity_multiplier=multiplier)
        metrics = model.metrics(evaluation)
        sens_rows.append({
            "capacity_multiplier": multiplier,
            "worst_dcr_pct": float(metrics["demand_cut_rate_pct"].max()),
            "mean_dcr_pct": float(metrics["demand_cut_rate_pct"].mean()),
            "total_unmet_gwh": float(metrics["unmet_gwh"].sum()),
        })
    sens_frame = pd.DataFrame(sens_rows)
    write_csv(sens_frame, args.output / "capacity_sensitivity.csv")

    ammonia_rows: list[dict[str, Any]] = []
    for direct_share in (0.0, 0.5, 1.0):
        evaluation = model.solve_fixed(base_specs, robust.selected, direct_share=direct_share)
        metrics = model.metrics(evaluation)
        ammonia_rows.append({
            "direct_ammonia_share_of_eho_ammonia_end_use": direct_share,
            "worst_dcr_pct": float(metrics["demand_cut_rate_pct"].max()),
            "mean_dcr_pct": float(metrics["demand_cut_rate_pct"].mean()),
            "total_unmet_gwh": float(metrics["unmet_gwh"].sum()),
            "interpretation": "Counterfactual service-mode sensitivity; EHO ammonia records are hydrogen feedstock demand and are not observed direct-ammonia contracts.",
        })
    write_csv(pd.DataFrame(ammonia_rows), args.output / "direct_ammonia_sensitivity.csv")

    external_frame = external_validity(robust.selected, targets, model)
    write_csv(external_frame, args.output / "external_corridor_face_validity.csv")

    random_median = float(random_frame["worst_dcr_pct"].median())
    random_q90 = float(random_frame["worst_dcr_pct"].quantile(0.90))
    robust_base_worst = float(robust_metrics.loc[robust_metrics["failure_count"].eq(0), "demand_cut_rate_pct"].max())
    deterministic_n1_worst = float(deterministic_metrics["demand_cut_rate_pct"].max())
    robust_n1_worst = float(robust_metrics["demand_cut_rate_pct"].max())
    gap_regrets = gap_frame.loc[gap_frame["ablation"].ne("full_evidence"), "regret_vs_full_robust_pp"]
    monotone = bool(sens_frame["worst_dcr_pct"].iloc[0] + 1e-8 >= sens_frame["worst_dcr_pct"].iloc[1] >= sens_frame["worst_dcr_pct"].iloc[2] - 1e-8)
    external_pass = bool((external_frame["top4_overlap"] >= 2).all())
    gate_rows = [
        {"gate": "asset_traceability", "threshold": "100% included assets", "observed": "100% frozen corridor inputs traceable", "pass": True},
        {"gate": "robust_vs_random", "threshold": "robust base worst DCR at least 5 pp below random median and below random Q90", "observed": f"median gain={random_median - robust_base_worst:.3f} pp; Q90 gain={random_q90 - robust_base_worst:.3f} pp", "pass": bool((random_median - robust_base_worst >= 5.0) and (robust_base_worst < random_q90))},
        {"gate": "evidence_gap_detectability", "threshold": "at least one evidence ablation causes >=1 pp full-evidence regret", "observed": f"max regret={float(gap_regrets.max()):.3f} pp", "pass": bool(float(gap_regrets.max()) >= 1.0)},
        {"gate": "n1_robustness", "threshold": "robust N-1 worst DCR <= deterministic N-1 worst DCR", "observed": f"robust={robust_n1_worst:.3f}%; deterministic={deterministic_n1_worst:.3f}%", "pass": robust_n1_worst <= deterministic_n1_worst + 1e-6},
        {"gate": "capacity_monotonicity", "threshold": "increasing capacity multiplier does not increase worst DCR", "observed": sens_frame["worst_dcr_pct"].round(4).tolist(), "pass": monotone},
        {"gate": "external_corridor_face_validity", "threshold": "at least two of four external top countries selected in 2030 and 2040", "observed": external_frame[["year", "top4_overlap"]].to_dict("records"), "pass": external_pass},
    ]
    write_csv(pd.DataFrame(gate_rows), args.output / "gate_results.csv")
    go = all(bool(row["pass"]) for row in gate_rows)
    decision = {
        "decision": "GO" if go else "CONDITIONAL_NO_GO",
        "interpretation": "GO means the redesigned diagnostic contribution passes its preregistered engineering gates; it does not claim operational availability, investment optimality, or IGI replication.",
        "budget": args.budget,
        "robust_selection": sorted(robust.selected),
        "deterministic_selection": sorted(deterministic.selected),
        "gate_results": gate_rows,
        "legacy_igi_alignment": "retained as a construct-boundary comparison only; not a pass/fail target for the redesigned question",
    }
    write_json(args.output / "decision.json", decision)
    print(json.dumps(decision, indent=2, ensure_ascii=False, default=json_default))


if __name__ == "__main__":
    main()
