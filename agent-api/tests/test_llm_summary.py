import unittest
from unittest.mock import patch

from app.llm import LLMCompletion, LLMConfig, build_summary_messages, get_llm_config
from app.llm.client import build_chat_completions_payload
from app.models import TicketCreateRequest
from app.tools import ToolCallResult
from app.workflow import run_agent_workflow


ENABLED_CONFIG = LLMConfig(
    enabled=True,
    provider="openai",
    api_key="test-key",
    model="fake-model",
    base_url="https://example.test/v1",
    timeout_seconds=1,
)


class FakeRegistry:
    def run(self, name: str, tool_input: dict):
        if name == "get_account":
            return ToolCallResult(name=name, input=tool_input, output={"id": tool_input["account_id"], "balance": 1000}, status="succeeded", elapsed_ms=1)
        if name == "list_account_transactions":
            return ToolCallResult(name=name, input=tool_input, output={"entries": []}, status="succeeded", elapsed_ms=1)
        if name == "check_account_reconciliation":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"current_balance": 1000, "latest_ledger_balance_after": 1000, "matched": True, "issues": []},
                status="succeeded",
                elapsed_ms=1,
            )
        if name == "get_transaction_detail":
            return ToolCallResult(name=name, input=tool_input, output={}, status="succeeded", elapsed_ms=1)
        raise AssertionError(f"unexpected tool: {name}")


class SuccessLLMClient:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete_json(self, messages: list[dict[str, str]], config: LLMConfig) -> LLMCompletion:
        self.messages = messages
        self.config = config
        return LLMCompletion(content=self.content, elapsed_ms=6)


class ErrorLLMClient:
    def complete_json(self, messages: list[dict[str, str]], config: LLMConfig) -> LLMCompletion:
        raise RuntimeError("fake model timeout")


class LLMSummaryWorkflowTest(unittest.TestCase):
    def test_prompt_contains_json_example_and_guardrails(self) -> None:
        messages = build_summary_messages(
            {
                "ticket_type": "reimbursement_policy",
                "title": "reimbursement",
                "description": "meal policy",
                "deterministic_summary": "deterministic",
                "evidence": [],
                "tool_calls": [],
                "needs_human": True,
                "escalation_reason": "needs review",
            }
        )
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("Example JSON output", combined)
        self.assertIn('"summary"', combined)
        self.assertIn('"needs_human"', combined)
        self.assertIn('"escalation_reason"', combined)
        self.assertIn('"confidence"', combined)
        self.assertIn("Do not invent reimbursement rules", combined)
        self.assertIn("Never cancel a human escalation", combined)

    def test_deepseek_config_reads_max_tokens(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LLM_ENABLED": "true",
                "LLM_PROVIDER": "deepseek",
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "deepseek-v4-flash",
                "LLM_TIMEOUT_SECONDS": "20",
                "LLM_MAX_TOKENS": "600",
            },
            clear=True,
        ):
            config = get_llm_config()

        self.assertTrue(config.available)
        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.model, "deepseek-v4-flash")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.timeout_seconds, 20)
        self.assertEqual(config.max_tokens, 600)

    def test_chat_completions_payload_uses_json_object_and_max_tokens(self) -> None:
        payload = build_chat_completions_payload([{"role": "user", "content": "Return JSON."}], ENABLED_CONFIG)

        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_tokens"], ENABLED_CONFIG.max_tokens)
        self.assertEqual(payload["model"], ENABLED_CONFIG.model)

    def test_disabled_llm_keeps_deterministic_summary_and_records_skip(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(title="reimbursement policy", description="What materials are needed for travel meal reimbursement?"),
            registry=FakeRegistry(),
            llm_config=LLMConfig(),
        )

        self.assertEqual(ticket.status, "completed")
        self.assertIn("llm_skipped", [event.event_type for event in ticket.trace])
        self.assertNotEqual(ticket.result.summary, "LLM refined summary")

    def test_successful_llm_json_updates_summary_and_records_call(self) -> None:
        client = SuccessLLMClient(
            '{"summary":"LLM refined summary","needs_human":false,"escalation_reason":null,"confidence":"high"}'
        )
        ticket = run_agent_workflow(
            TicketCreateRequest(title="reimbursement policy", description="What materials are needed for travel meal reimbursement?"),
            registry=FakeRegistry(),
            llm_config=ENABLED_CONFIG,
            llm_client=client,
        )

        self.assertEqual(ticket.result.summary, "LLM refined summary")
        self.assertIn("llm_call", [event.event_type for event in ticket.trace])
        llm_event = [event for event in ticket.trace if event.event_type == "llm_call"][0]
        self.assertEqual(llm_event.payload["prompt_version"], "finance_ticket_summary_v1")
        self.assertNotIn("test-key", str(llm_event.payload))

    def test_invalid_json_falls_back_to_deterministic_summary(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(title="reimbursement policy", description="What materials are needed for travel meal reimbursement?"),
            registry=FakeRegistry(),
            llm_config=ENABLED_CONFIG,
            llm_client=SuccessLLMClient("not json"),
        )

        self.assertNotEqual(ticket.result.summary, "not json")
        self.assertIn("llm_fallback", [event.event_type for event in ticket.trace])

    def test_model_exception_falls_back_to_deterministic_summary(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(title="reimbursement policy", description="What materials are needed for travel meal reimbursement?"),
            registry=FakeRegistry(),
            llm_config=ENABLED_CONFIG,
            llm_client=ErrorLLMClient(),
        )

        self.assertEqual(ticket.status, "completed")
        self.assertIn("llm_fallback", [event.event_type for event in ticket.trace])

    def test_llm_cannot_cancel_human_escalation(self) -> None:
        ticket = run_agent_workflow(
            TicketCreateRequest(title="unsupported budget forecast", description="Forecast next quarter profit."),
            registry=FakeRegistry(),
            llm_config=ENABLED_CONFIG,
            llm_client=SuccessLLMClient(
                '{"summary":"Model says no escalation is needed.","needs_human":false,"escalation_reason":null,"confidence":"high"}'
            ),
        )

        self.assertEqual(ticket.status, "escalated")
        self.assertTrue(ticket.result.needs_human)
        self.assertIsNotNone(ticket.result.escalation_reason)


if __name__ == "__main__":
    unittest.main()
