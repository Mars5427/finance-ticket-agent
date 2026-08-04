import unittest

from fastapi.testclient import TestClient

from app import main
from app.store import store
from app.tools import ToolCallResult


class FakeRegistry:
    def run(self, name: str, tool_input: dict):
        if name == "get_account":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"id": tool_input["account_id"], "balance": 1000, "currency": "USD"},
                status="succeeded",
                elapsed_ms=1,
            )
        if name == "list_account_transactions":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={
                    "entries": [
                        {
                            "transfer_id": "transfer-demo",
                            "account_id": tool_input["account_id"],
                            "direction": "debit",
                            "amount": 500,
                            "balance_after": 1000,
                        }
                    ]
                },
                status="succeeded",
                elapsed_ms=1,
            )
        if name == "get_transaction_detail":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"id": tool_input["transfer_id"], "amount": 500, "status": "succeeded"},
                status="succeeded",
                elapsed_ms=1,
            )
        if name == "check_account_reconciliation":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={
                    "account_id": tool_input["account_id"],
                    "current_balance": 1000,
                    "latest_ledger_balance_after": 1000,
                    "matched": True,
                    "issues": [],
                },
                status="succeeded",
                elapsed_ms=1,
            )
        raise AssertionError(f"unexpected tool: {name}")


class TicketContinueTest(unittest.TestCase):
    def setUp(self) -> None:
        store.clear()
        main.tool_registry = FakeRegistry()
        self.client = TestClient(main.app)

    def test_continue_missing_balance_ticket_updates_same_ticket(self) -> None:
        created = self.client.post(
            "/api/tickets",
            json={"title": "balance anomaly", "description": "The account balance looks wrong.", "metadata": {}},
        )
        self.assertEqual(created.status_code, 200)
        initial = created.json()
        self.assertEqual(initial["status"], "needs_more_info")

        continued = self.client.post(
            f"/api/tickets/{initial['id']}/continue",
            json={
                "message": "account is demo-account and observed balance is 1500",
                "metadata_patch": {"account_id": "demo-account", "observed_balance": 1500},
            },
        )

        self.assertEqual(continued.status_code, 200)
        ticket = continued.json()
        self.assertEqual(ticket["id"], initial["id"])
        self.assertEqual(ticket["status"], "completed")
        self.assertEqual(ticket["metadata"]["account_id"], "demo-account")
        self.assertEqual(ticket["metadata"]["observed_balance"], 1500)
        self.assertTrue(ticket["result"]["tool_calls"])

        event_types = [event["event_type"] for event in ticket["trace"]]
        self.assertIn("missing_parameters", event_types)
        self.assertIn("continue_ticket", event_types)
        self.assertIn("metadata_patch_applied", event_types)
        self.assertIn("dialogue_context_updated", event_types)
        self.assertEqual(len(ticket["dialogue_context"]), 2)
        self.assertIn("balance anomaly", ticket["dialogue_context"][0]["content"])
        self.assertIn("observed balance is 1500", ticket["dialogue_context"][1]["content"])

    def test_continue_missing_ticket_returns_404(self) -> None:
        response = self.client.post(
            "/api/tickets/missing/continue",
            json={"message": "account is demo", "metadata_patch": {"account_id": "demo"}},
        )

        self.assertEqual(response.status_code, 404)

    def test_continue_rejects_non_object_metadata_patch(self) -> None:
        created = self.client.post(
            "/api/tickets",
            json={"title": "balance anomaly", "description": "The account balance looks wrong.", "metadata": {}},
        ).json()

        response = self.client.post(
            f"/api/tickets/{created['id']}/continue",
            json={"message": "account is demo", "metadata_patch": ["not", "object"]},
        )

        self.assertEqual(response.status_code, 422)

    def test_continue_completed_ticket_returns_409(self) -> None:
        created = self.client.post(
            "/api/tickets",
            json={
                "title": "reimbursement policy",
                "description": "What materials are needed for travel meal reimbursement?",
                "metadata": {},
            },
        )
        self.assertEqual(created.status_code, 200)
        ticket = created.json()
        self.assertEqual(ticket["status"], "completed")

        response = self.client.post(
            f"/api/tickets/{ticket['id']}/continue",
            json={"message": "extra info", "metadata_patch": {"account_id": "demo-account"}},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("only needs_more_info tickets can be continued", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
