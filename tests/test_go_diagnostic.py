"""Regression tests for the public-data redesign and its audit diagnostics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from go_diagnostic import EvidencePortfolioMILP  # noqa: E402


class GoDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = EvidencePortfolioMILP(PROJECT / "data" / "corridor_2024")
        cls.selected = {
            "LH2_Tk_BE|BEh2",
            "LH2_Tk_DE|DEh2",
            "LH2_Tk_FRn|FRh2N",
            "LH2_Tk_NL|NLh2",
        }

    def test_candidate_groups_are_traceable_and_unique(self) -> None:
        self.assertEqual(len(self.model.candidate_keys), 9)
        self.assertEqual(len(set(self.model.candidate_keys)), 9)
        self.assertTrue(all("|" in key for key in self.model.candidate_keys))
        self.assertEqual(len(self.selected), 4)

    def test_fixed_selection_filters_nonselected_terminal_edges(self) -> None:
        solution = self.model.solve_fixed(
            self.model.specs([self.model.central_scenario()]), self.selected
        )
        flows = self.model.flow_metrics(solution)
        active_terminal = flows[
            flows["edge_type"].eq("terminal_backbone") & flows["flow_gwh"].gt(1.0e-7)
        ]
        self.assertTrue(set(active_terminal["candidate_key"]).issubset(self.selected))
        self.assertLess(float(self.model.metrics(solution).iloc[0]["demand_cut_rate_pct"]), 100.0)

    def test_selector_epigraph_matches_evaluated_worst_cut_rate(self) -> None:
        solution = self.model.solve_selector(
            self.model.specs(self.model.core_scenarios()), mode="full", budget=4
        )
        fixed = self.model.solve_fixed(
            self.model.specs(self.model.core_scenarios()), solution.selected
        )
        observed = float(self.model.metrics(fixed)["demand_cut_rate_pct"].max() / 100.0)
        fitted = float(solution.problem.metadata["stage1_worst_dcr"])
        self.assertTrue(np.isclose(observed, fitted, atol=1.0e-7, rtol=0.0))

    def test_n_minus_two_failure_labels_preserve_failure_count(self) -> None:
        specs = self.model.nk_specs([self.model.central_scenario()], self.selected, 2)
        solution = self.model.solve_fixed(specs, self.selected)
        metrics = self.model.metrics(solution)
        self.assertTrue((metrics.loc[metrics["failure_count"].eq(2), "failure_count"] == 2).all())

    def test_direct_ammonia_is_only_a_counterfactual_split(self) -> None:
        scenario = self.model.central_scenario()
        base = self.model._demand_rows(scenario, direct_share=0.0)
        counterfactual = self.model._demand_rows(scenario, direct_share=0.5)
        base_total = sum(float(row["target"]) for row in base)
        counter_total = sum(float(row["target"]) for row in counterfactual)
        self.assertTrue(np.isclose(base_total, counter_total, atol=1.0e-7, rtol=0.0))
        self.assertFalse(any(row["service"] == "nh3_direct" for row in base))
        self.assertTrue(any(row["service"] == "nh3_direct" for row in counterfactual))


if __name__ == "__main__":
    unittest.main(verbosity=2)
