import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.models import TicketCreateRequest
from app.rag.documents import load_markdown_chunks
from app.rag.retriever import retrieve_evidence
from app.tools import ToolCallResult
from app.workflow import run_agent_workflow


class FakeRegistry:
    def run(self, name: str, tool_input: dict):
        if name == "list_account_transactions":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"entries": [{"transfer_id": "transfer-1", "direction": "debit", "amount": 100, "balance_after": 1000}]},
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
        if name == "get_account":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"id": tool_input["account_id"], "balance": 1000, "currency": "USD"},
                status="succeeded",
                elapsed_ms=1,
            )
        if name == "get_transaction_detail":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"id": tool_input["transfer_id"], "amount": 100, "status": "succeeded"},
                status="succeeded",
                elapsed_ms=1,
            )
        raise AssertionError(f"unexpected tool: {name}")


class RagTest(unittest.TestCase):
    def test_markdown_ingestion_splits_heading_chunks(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.md"
            path.write_text("# Root\n\nintro\n\n## Meals\n\nmeal policy\n\nsecond paragraph", encoding="utf-8")

            chunks = load_markdown_chunks(path)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[1].source, "policy.md")
        self.assertEqual(chunks[1].heading, "Meals")
        self.assertIn("meal policy", chunks[1].content)

    def test_reimbursement_query_hits_policy_or_approval_rules(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(title="报销规则", description="出差餐补需要哪些材料？"),
            registry=FakeRegistry(),
        )

        sources = {item["source"] for item in ticket.result.evidence}
        self.assertEqual(ticket.status, "completed")
        self.assertTrue({"reimbursement-policy.md", "approval-rules.md"} & sources)
        self.assertTrue(all("score" in item for item in ticket.result.evidence))
        self.assertIn("rag_retrieval", [event.event_type for event in ticket.trace])

    def test_no_evidence_does_not_fabricate_answer(self) -> None:
        results, meta = retrieve_evidence(
            "火星基地设备补贴完全无关条款",
            sources=["reimbursement-policy.md"],
            min_score=0.9,
        )

        self.assertEqual(results, [])
        self.assertIsNotNone(meta["no_evidence_reason"])

    def test_reimbursement_without_evidence_escalates(self) -> None:
        with patch(
            "app.workflow.retrieve_knowledge_evidence",
            return_value=(
                [],
                {
                    "query": "报销规则",
                    "matched_sources": [],
                    "snippets": [],
                    "scores": [],
                    "elapsed_ms": 0,
                    "no_evidence_reason": "knowledge base did not contain a strong enough matching chunk",
                },
            ),
        ):
            ticket = run_agent_workflow(
                TicketCreateRequest(title="报销规则", description="火星基地设备补贴能不能报销？"),
                registry=FakeRegistry(),
            )

        self.assertEqual(ticket.type, "reimbursement_policy")
        self.assertEqual(ticket.status, "escalated")
        self.assertEqual(ticket.result.evidence, [])
        self.assertIn("知识库未检索到足够依据", ticket.result.summary)

    def test_reconciliation_ticket_returns_sop_evidence(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(
                title="对账差异",
                description="这个账户本月对账差了 1000，帮我定位原因。",
                metadata={"account_id": "demo-account", "expected_balance": 900, "time_range": "2026-08"},
            ),
            registry=FakeRegistry(),
        )

        self.assertEqual(ticket.type, "reconciliation_anomaly")
        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.evidence)
        self.assertEqual({item["source"] for item in ticket.result.evidence}, {"reconciliation-sop.md"})
        self.assertIn("对账 SOP 依据", ticket.result.summary)

    def test_trace_contains_rag_retrieval_event(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(title="报销规则", description="缺少发票能不能报销？"),
            registry=FakeRegistry(),
        )
        rag_events = [event for event in ticket.trace if event.event_type == "rag_retrieval"]

        self.assertEqual(len(rag_events), 1)
        self.assertIn("query", rag_events[0].payload)
        self.assertIn("matched_sources", rag_events[0].payload)
        self.assertIn("scores", rag_events[0].payload)


if __name__ == "__main__":
    unittest.main()
