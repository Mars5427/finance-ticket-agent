import unittest

from app.tools.go_client import GoAPIError
from app.tools.registry import ToolCallResult, build_registry


class FakeGoClient:
    def get_account(self, account_id: str):
        return {"id": account_id, "balance": 1000, "currency": "USD"}

    def list_account_transactions(self, account_id: str, limit: int = 50):
        return {"entries": [{"transfer_id": "transfer-1", "account_id": account_id, "balance_after": 1000}]}

    def get_transaction_detail(self, transfer_id: str):
        return {"id": transfer_id, "status": "succeeded", "amount": 500}

    def check_account_reconciliation(self, account_id: str):
        return {"account_id": account_id, "current_balance": 1000, "latest_ledger_balance_after": 1000, "matched": True, "issues": []}


class FailingGoClient(FakeGoClient):
    def get_account(self, account_id: str):
        raise GoAPIError(status_code=404, code="NOT_FOUND", message="resource was not found", payload={"error": {"code": "NOT_FOUND"}})


class ToolRegistryTest(unittest.TestCase):
    def test_registry_exposes_four_mcp_style_tools(self) -> None:
        registry = build_registry(FakeGoClient())
        tools = registry.list_tools()

        self.assertEqual(
            [tool["name"] for tool in tools],
            ["get_account", "list_account_transactions", "get_transaction_detail", "check_account_reconciliation"],
        )
        for tool in tools:
            self.assertIn("description", tool)
            self.assertIn("input_schema", tool)
            self.assertIn("output_schema", tool)

    def test_tool_success_result_contains_output_and_elapsed(self) -> None:
        registry = build_registry(FakeGoClient())
        result = registry.run("get_account", {"account_id": "account-1"})

        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output["id"], "account-1")
        self.assertIsNone(result.error)

    def test_tool_error_mapping_returns_failed_result(self) -> None:
        registry = build_registry(FailingGoClient())
        result = registry.run("get_account", {"account_id": "missing"})

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.output["code"], "NOT_FOUND")
        self.assertEqual(result.output["status_code"], 404)
        self.assertEqual(result.error, "resource was not found")


if __name__ == "__main__":
    unittest.main()
