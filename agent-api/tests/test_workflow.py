import unittest

from app.models import TicketCreateRequest
from app.tools import ToolCallResult
from app.workflow import run_deterministic_workflow


class FakeRegistry:
    def __init__(self, reconciliation_output: dict | None = None) -> None:
        self.reconciliation_output = reconciliation_output or {
            "account_id": "demo-account",
            "current_balance": 1000,
            "latest_ledger_balance_after": 1000,
            "matched": True,
            "issues": [],
        }

    def run(self, name: str, tool_input: dict):
        if name == "get_account":
            return ToolCallResult(name=name, input=tool_input, output={"id": tool_input["account_id"], "balance": 1000, "currency": "USD"}, status="succeeded", elapsed_ms=1)
        if name == "list_account_transactions":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={
                    "entries": [
                        {
                            "id": 1,
                            "transfer_id": "transfer-demo",
                            "account_id": tool_input["account_id"],
                            "direction": "debit",
                            "amount": 500,
                            "balance_after": 1000,
                        }
                    ]
                },
                status="succeeded",
                elapsed_ms=2,
            )
        if name == "get_transaction_detail":
            return ToolCallResult(name=name, input=tool_input, output={"id": tool_input["transfer_id"], "amount": 500, "status": "succeeded"}, status="succeeded", elapsed_ms=3)
        if name == "check_account_reconciliation":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={**self.reconciliation_output, "account_id": tool_input["account_id"]},
                status="succeeded",
                elapsed_ms=4,
            )
        raise AssertionError(f"unexpected tool: {name}")


class FailingRegistry(FakeRegistry):
    def run(self, name: str, tool_input: dict):
        if name == "get_account":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"code": "GO_API_UNAVAILABLE"},
                status="failed",
                elapsed_ms=5,
                error="connection refused",
            )
        return super().run(name, tool_input)


class LangGraphWorkflowTest(unittest.TestCase):
    def test_reimbursement_ticket_completes_with_evidence(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(title="报销规则", description="出差餐补需要哪些材料？"),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.type, "reimbursement_policy")
        self.assertEqual(ticket.status, "completed")
        self.assertTrue(ticket.result.evidence)
        self.assertEqual(ticket.trace[0].step, "initialize_context")
        self.assertIn("classify", [event.step for event in ticket.trace])

    def test_balance_ticket_asks_for_missing_parameters(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(title="余额异常", description="账户余额比预期少了 500"),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.type, "balance_anomaly")
        self.assertEqual(ticket.status, "needs_more_info")
        self.assertIn("账户 ID", ticket.result.follow_up_question or "")
        self.assertEqual(ticket.result.tool_calls, [])

    def test_balance_ticket_calls_tools_when_fields_exist(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="余额异常",
                description="账户余额比预期少了 500",
                metadata={"account_id": "demo-account", "observed_balance": 1500},
            ),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.status, "completed")
        self.assertEqual([call["name"] for call in ticket.result.tool_calls], ["get_account", "list_account_transactions", "get_transaction_detail"])
        self.assertEqual([call["status"] for call in ticket.result.tool_calls], ["succeeded", "succeeded", "succeeded"])
        self.assertIn("tool_call", [event.event_type for event in ticket.trace])
        self.assertIn("execute_tools", [event.step for event in ticket.trace])

    def test_reconciliation_completes_when_internal_and_expected_balances_match(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="对账差异",
                description="这个账户本月对账差了 1000",
                metadata={"account_id": "demo-account", "expected_balance": 1000, "time_range": "2026-08"},
            ),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.type, "reconciliation_anomaly")
        self.assertEqual(ticket.status, "completed")
        self.assertFalse(ticket.result.needs_human)
        self.assertEqual([call["name"] for call in ticket.result.tool_calls], ["list_account_transactions", "check_account_reconciliation"])

    def test_reconciliation_escalates_when_expected_balance_differs_from_current_balance(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="对账差异",
                description="这个账户本月对账差了 1000",
                metadata={"account_id": "demo-account", "expected_balance": 3000, "time_range": "2026-08"},
            ),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.needs_human)
        self.assertIn("外部对账单", ticket.result.summary)
        self.assertIn("2000", ticket.result.escalation_reason or "")
        self.assertTrue(any("summary" in event.payload for event in ticket.trace))

    def test_reconciliation_classification_wins_when_text_mentions_balance(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="account reconciliation anomaly",
                description="The external statement balance differs from the internal account balance.",
                metadata={"account_id": "demo-account", "expected_balance": 3000, "time_range": "2026-08"},
            ),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.type, "reconciliation_anomaly")
        self.assertEqual(ticket.status, "escalated")

    def test_reconciliation_escalates_when_expected_balance_is_not_numeric(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="对账差异",
                description="这个账户本月对账差了 1000",
                metadata={"account_id": "demo-account", "expected_balance": "not-a-number", "time_range": "2026-08"},
            ),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.needs_human)
        self.assertIn("无法转换为整数", ticket.result.summary)

    def test_reconciliation_escalates_when_go_internal_reconciliation_mismatches(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="对账差异",
                description="这个账户本月对账差了 1000",
                metadata={"account_id": "demo-account", "expected_balance": 1000, "time_range": "2026-08"},
            ),
            registry=FakeRegistry(
                reconciliation_output={
                    "current_balance": 1000,
                    "latest_ledger_balance_after": 900,
                    "matched": False,
                    "issues": ["BALANCE_MISMATCH"],
                }
            ),
        )

        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.needs_human)
        self.assertIn("matched=false", ticket.result.summary)

    def test_tool_failure_triggers_human_escalation(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(
                title="余额异常",
                description="账户余额比预期少了 500",
                metadata={"account_id": "demo-account", "observed_balance": 1500},
            ),
            registry=FailingRegistry(),
        )

        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.needs_human)
        self.assertIn("工具调用失败", ticket.result.summary)
        self.assertEqual(ticket.result.tool_calls[0]["status"], "failed")

    def test_unsupported_ticket_triggers_human_escalation(self) -> None:
        ticket = run_deterministic_workflow(
            TicketCreateRequest(title="预算预测", description="帮我预测下季度利润"),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.type, "unsupported")
        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.needs_human)
        self.assertEqual(ticket.result.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
