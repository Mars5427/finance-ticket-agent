import unittest
from pathlib import Path

from app.evaluation.runner import load_cases, run_evaluation


class EvaluationRunnerTest(unittest.TestCase):
    def test_loads_fixed_eval_cases(self) -> None:
        cases = load_cases()

        self.assertGreaterEqual(len(cases), 10)
        self.assertTrue({"reimbursement_policy", "balance_anomaly", "reconciliation_anomaly"} <= {case.expected_type for case in cases})
        self.assertTrue(any(case.continue_request for case in cases))

    def test_run_evaluation_calculates_required_metrics(self) -> None:
        summary = run_evaluation()

        self.assertGreaterEqual(summary["total_cases"], 10)
        self.assertIn("task_completion_rate", summary)
        self.assertIn("average_tool_call_count", summary)
        self.assertIn("human_escalation_ratio", summary)
        self.assertIn("failure_type_distribution", summary)
        self.assertGreater(summary["average_tool_call_count"], 0)
        self.assertGreaterEqual(summary["status_match_rate"], 0)
        self.assertLessEqual(summary["status_match_rate"], 1)

    def test_failure_type_distribution_contains_expected_boundaries(self) -> None:
        summary = run_evaluation()
        distribution = summary["failure_type_distribution"]

        self.assertIn("no_evidence", distribution)
        self.assertIn("tool_failure", distribution)
        self.assertIn("missing_parameters", distribution)
        self.assertIn("expected_balance_mismatch", distribution)
        self.assertIn("internal_reconciliation_mismatch", distribution)
        self.assertIn("invalid_expected_balance", distribution)
        self.assertIn("unsupported_scope", distribution)
        self.assertEqual(distribution["internal_reconciliation_mismatch"], 1)
        self.assertEqual(distribution["invalid_expected_balance"], 1)

    def test_continue_case_is_evaluated(self) -> None:
        summary = run_evaluation()
        continue_results = [result for result in summary["results"] if result["continuation_used"]]

        self.assertEqual(len(continue_results), 1)
        self.assertEqual(summary["continuation_success_rate"], 1.0)
        self.assertTrue(continue_results[0]["continuation_success"])
        self.assertIn("continue_ticket", continue_results[0]["trace_events"])
        self.assertGreaterEqual(continue_results[0]["tool_call_count"], 1)

    def test_evaluation_uses_default_llm_disabled_path(self) -> None:
        summary = run_evaluation()

        self.assertTrue(any("LLM is disabled for offline evaluation" in note for note in summary["notes"]))
        self.assertTrue(all("llm_skipped" in result["trace_events"] for result in summary["results"]))

    def test_script_entrypoint_exists(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_eval.py"

        self.assertTrue(script.exists())


if __name__ == "__main__":
    unittest.main()
