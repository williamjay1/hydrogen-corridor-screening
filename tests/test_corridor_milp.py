"""Regression tests for the public-data corridor screening model.

These tests intentionally use a single frozen scenario where possible.  They
check model properties rather than attempting to validate a planning model
against unobserved operations.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from corridor_milp import CorridorMILP, Scenario, TOLERANCE  # noqa: E402


class CorridorMILPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CorridorMILP()
        cls.scenario = Scenario("S2040_Advanced_medium", 2040, "Advanced", "medium")

    def test_frozen_data_are_traceable_and_direct_ammonia_is_not_admitted(self) -> None:
        data_dir = self.model.data_dir
        manifest = pd.read_csv(data_dir / "source_manifest.csv")
        self.assertTrue(manifest["sha256"].notna().all())
        self.assertTrue(manifest["bytes"].gt(0).all())
        self.assertTrue(self.model.interfaces["traceable"].all())
        self.assertFalse(self.model.facilities["direct_ammonia_eligible"].any())
        self.assertNotIn("NH3_direct", set(self.model.carriers))

    def test_star_lp_is_its_documented_capacity_upper_bound(self) -> None:
        result = self.model.solve_star_lp([self.scenario]).iloc[0]
        edges = self.model.scenario_edges(self.scenario, star=True)
        sources = self.model.source_has_any_carrier(self.scenario)
        capacity = float(edges.loc[edges["edge_id"].isin(sources), "capacity_gwh_per_year"].sum())
        self.assertAlmostEqual(float(result["served_gwh"]), min(capacity, float(result["total_demand_gwh"])), places=6)

    def test_graph_lp_respects_capacity_and_flow_constraints(self) -> None:
        solution = self.model.solve_graph_lp([self.scenario], compatibility=True)
        audit = self.model.audit_solution(solution)
        self.assertLessEqual(audit["max_constraint_violation"], 1.0e-5)
        self.assertLessEqual(audit["max_bound_violation"], 1.0e-7)
        _, _, flows, _ = self.model.metrics(solution)
        aggregate = flows[flows["carrier"].eq("__aggregate__")]
        self.assertTrue((aggregate["flow_gwh"] <= aggregate["capacity_gwh"] + 1.0e-5).all())

    def test_state_year_and_carrier_compatibility_are_enforced(self) -> None:
        edges_2030 = self.model.scenario_edges(Scenario("S2030_PCIPMI_medium", 2030, "PCI/PMI", "medium"))
        self.assertFalse(
            ((edges_2030["from_node"] == "LH2_Tk_FRn") & (edges_2030["edge_type"] == "terminal_backbone")).any(),
            "A zero-capacity 2030 France terminal edge must not be available.",
        )
        solution = self.model.solve_graph_lp([self.scenario], compatibility=True)
        _, _, flows, _ = self.model.metrics(solution)
        lookup = self.model.carrier_lookup(self.scenario)
        terminal_flows = flows[
            flows["edge_type"].eq("terminal_backbone")
            & ~flows["carrier"].eq("__aggregate__")
            & flows["flow_gwh"].gt(TOLERANCE)
        ]
        for _, row in terminal_flows.iterrows():
            self.assertIn(row["carrier"], lookup[str(row["edge_id"])])

    def test_country_carrier_pool_is_not_replicated_over_terminal_groups(self) -> None:
        solution = self.model.solve_graph_lp([self.scenario], compatibility=True)
        _, _, flows, _ = self.model.metrics(solution)
        terminal_flows = flows[
            flows["edge_type"].eq("terminal_backbone")
            & ~flows["carrier"].eq("__aggregate__")
        ].merge(
            self.model.edges[["edge_id", "year", "from_country"]], on="edge_id", how="left", validate="many_to_one"
        )
        observed = terminal_flows.groupby(["from_country", "carrier"], as_index=False)["flow_gwh"].sum()
        pools = self.model.carrier_pools[self.model.carrier_pools["year"].eq(2040)].copy()
        for _, row in observed.iterrows():
            pool = pools[
                pools["country"].eq(row["from_country"])
                & pools["carrier_class"].eq(row["carrier"])
            ]
            self.assertEqual(len(pool), 1)
            self.assertLessEqual(
                float(row["flow_gwh"]),
                float(pool.iloc[0]["carrier_evidence_capacity_gwh_per_day"]) * 365.0 + 1.0e-5,
            )

    def test_carrier_evidence_has_no_duplicate_assets_and_logs_conflicts(self) -> None:
        evidence = pd.read_csv(self.model.data_dir / "carrier_project_evidence.csv")
        exclusions = pd.read_csv(self.model.data_dir / "exclusion_ledger.csv")
        self.assertFalse(evidence["asset_id"].duplicated().any())
        self.assertTrue(exclusions["reason"].eq("carrier_field_conflicts_with_project_name").any())

    def test_deterministic_lp_repeats_exactly_with_frozen_inputs(self) -> None:
        first = self.model.solve_graph_lp([self.scenario], compatibility=True)
        second = self.model.solve_graph_lp([self.scenario], compatibility=True)
        self.assertTrue(np.isclose(first.result.fun, second.result.fun, atol=1.0e-7, rtol=0.0))
        self.assertEqual(first.problem.variable_index, second.problem.variable_index)


if __name__ == "__main__":
    unittest.main(verbosity=2)
