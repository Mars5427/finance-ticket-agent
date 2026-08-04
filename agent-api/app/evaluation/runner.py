from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.llm import LLMConfig
from app.models import TicketCreateRequest, TicketResponse
from app.tools import ToolCallResult
from app.workflow import run_agent_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_PATH = PROJECT_ROOT / "eval_cases" / "finance_tickets.json"


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    title: str
    description: str
    metadata: dict[str, Any]
    expected_type: str
    expected_status: str
    expected_min_tool_calls: int
    expected_needs_human: bool
    expected_trace_events: list[str]
    continue_request: dict[str, Any] | None = None
    rag_mode: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    expected_type: str
    actual_type: str
    expected_status: str
    actual_status: str
    expected_needs_human: bool
    actual_needs_human: bool
    tool_call_count: int
    evidence_count: int
    trace_events: list[str]
    continuation_used: bool
    continuation_success: bool | None
    passed: bool
    failure_types: list[str]
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "expected_type": self.expected_type,
            "actual_type": self.actual_type,
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "expected_needs_human": self.expected_needs_human,
            "actual_needs_human": self.actual_needs_human,
            "tool_call_count": self.tool_call_count,
            "evidence_count": self.evidence_count,
            "trace_events": self.trace_events,
            "continuation_used": self.continuation_used,
            "continuation_success": self.continuation_success,
            "passed": self.passed,
            "failure_types": self.failure_types,
            "summary": self.summary,
        }


class EvaluationFakeRegistry:
    def run(self, name: str, tool_input: dict[str, Any]) -> ToolCallResult:
        account_id = str(tool_input.get("account_id", "demo-account"))
        if account_id == "tool-failure-account":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"code": "FAKE_TOOL_FAILURE"},
                status="failed",
                elapsed_ms=1,
                error=f"fake failure for {name}",
            )
        if name == "get_account":
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={"id": account_id, "balance": 1000, "currency": "USD"},
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
                            "id": 1,
                            "transfer_id": "transfer-demo",
                            "account_id": account_id,
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
            matched = account_id != "ledger-mismatch-account"
            return ToolCallResult(
                name=name,
                input=tool_input,
                output={
                    "account_id": account_id,
                    "current_balance": 1000,
                    "latest_ledger_balance_after": 1000 if matched else 900,
                    "matched": matched,
                    "issues": [] if matched else ["BALANCE_MISMATCH"],
                },
                status="succeeded",
                elapsed_ms=1,
            )
        raise AssertionError(f"unexpected tool: {name}")


def load_cases(path: Path | str = DEFAULT_CASES_PATH) -> list[EvaluationCase]:
    raw_cases = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EvaluationCase(
            id=item["id"],
            title=item["title"],
            description=item["description"],
            metadata=item.get("metadata", {}),
            expected_type=item["expected_type"],
            expected_status=item["expected_status"],
            expected_min_tool_calls=int(item.get("expected_min_tool_calls", 0)),
            expected_needs_human=bool(item.get("expected_needs_human", False)),
            expected_trace_events=list(item.get("expected_trace_events", [])),
            continue_request=item.get("continue_request"),
            rag_mode=item.get("rag_mode"),
        )
        for item in raw_cases
    ]


def run_evaluation(
    cases_path: Path | str = DEFAULT_CASES_PATH,
    registry: Any | None = None,
) -> dict[str, Any]:
    cases = load_cases(cases_path)
    fake_registry = registry or EvaluationFakeRegistry()
    results = [evaluate_case(case, fake_registry) for case in cases]
    return summarize_results(results)


def evaluate_case(case: EvaluationCase, registry: Any) -> EvaluationResult:
    request = TicketCreateRequest(title=case.title, description=case.description, metadata=case.metadata)
    if case.rag_mode == "force_no_evidence":
        with patch(
            "app.workflow.retrieve_knowledge_evidence",
            return_value=(
                [],
                {
                    "query": f"{case.title} {case.description}",
                    "matched_sources": [],
                    "snippets": [],
                    "scores": [],
                    "elapsed_ms": 0,
                    "no_evidence_reason": "forced no evidence for offline evaluation",
                },
            ),
        ):
            initial = run_agent_workflow(request, registry=registry, llm_config=LLMConfig())
            final = continue_if_needed(case, initial, registry)
    else:
        initial = run_agent_workflow(request, registry=registry, llm_config=LLMConfig())
        final = continue_if_needed(case, initial, registry)
    return build_result(case, initial, final)


def continue_if_needed(case: EvaluationCase, initial: TicketResponse, registry: Any) -> TicketResponse:
    if not case.continue_request:
        return initial
    patch_payload = case.continue_request.get("metadata_patch", {})
    continuation_request = TicketCreateRequest(
        title=initial.title,
        description=initial.description,
        metadata={**initial.metadata, **patch_payload},
    )
    return run_agent_workflow(
        continuation_request,
        registry=registry,
        ticket_id=initial.id,
        prior_dialogue_context=initial.dialogue_context,
        prior_trace=initial.trace,
        continuation_message=str(case.continue_request.get("message", "")),
        metadata_patch=patch_payload,
        created_at=initial.created_at,
        llm_config=LLMConfig(),
    )


def build_result(case: EvaluationCase, initial: TicketResponse, final: TicketResponse) -> EvaluationResult:
    trace_events = [event.event_type for event in final.trace]
    failure_types = classify_failure_types(case, final, trace_events)
    expected_events_present = all(event_type in trace_events for event_type in case.expected_trace_events)
    continuation_success = None
    if case.continue_request:
        continuation_success = (
            initial.id == final.id
            and initial.status == "needs_more_info"
            and final.status != "needs_more_info"
            and "continue_ticket" in trace_events
        )
    passed = (
        final.type == case.expected_type
        and final.status == case.expected_status
        and final.result.needs_human == case.expected_needs_human
        and len(final.result.tool_calls) >= case.expected_min_tool_calls
        and expected_events_present
        and (continuation_success is not False)
    )
    return EvaluationResult(
        case_id=case.id,
        expected_type=case.expected_type,
        actual_type=final.type,
        expected_status=case.expected_status,
        actual_status=final.status,
        expected_needs_human=case.expected_needs_human,
        actual_needs_human=final.result.needs_human,
        tool_call_count=len(final.result.tool_calls),
        evidence_count=len(final.result.evidence),
        trace_events=trace_events,
        continuation_used=bool(case.continue_request),
        continuation_success=continuation_success,
        passed=passed,
        failure_types=failure_types,
        summary=final.result.summary,
    )


def classify_failure_types(case: EvaluationCase, ticket: TicketResponse, trace_events: list[str]) -> list[str]:
    failures: list[str] = []
    if ticket.type != case.expected_type:
        failures.append("type_mismatch")
    if ticket.status != case.expected_status:
        failures.append("status_mismatch")
    if ticket.status == "needs_more_info":
        failures.append("missing_parameters")
    if ticket.type == "unsupported":
        failures.append("unsupported_scope")
    if "rag_retrieval" in trace_events and not ticket.result.evidence:
        failures.append("no_evidence")
    if any(call.get("status") != "succeeded" for call in ticket.result.tool_calls):
        failures.append("tool_failure")
    reason_text = f"{ticket.result.summary} {ticket.result.escalation_reason or ''}"
    if "expected_balance" in reason_text and "differs" in reason_text:
        failures.append("expected_balance_mismatch")
    if "matched=false" in reason_text or "BALANCE_MISMATCH" in reason_text:
        failures.append("internal_reconciliation_mismatch")
    if "expected_balance" in reason_text and ("not a valid integer" in reason_text or "无法转换为整数" in reason_text):
        failures.append("invalid_expected_balance")
    return sorted(set(failures))


def summarize_results(results: list[EvaluationResult]) -> dict[str, Any]:
    total_cases = len(results)
    completed_cases = sum(1 for result in results if result.actual_status == "completed")
    status_matches = sum(1 for result in results if result.actual_status == result.expected_status)
    human_escalations = sum(1 for result in results if result.actual_needs_human)
    rag_cases = [result for result in results if "rag_retrieval" in result.trace_events]
    continuation_cases = [result for result in results if result.continuation_used]
    failure_counter: Counter[str] = Counter()
    for result in results:
        failure_counter.update(result.failure_types)
    failure_distribution = {category: 0 for category in FAILURE_CATEGORIES}
    failure_distribution.update(dict(sorted(failure_counter.items())))

    summary = {
        "total_cases": total_cases,
        "passed_cases": sum(1 for result in results if result.passed),
        "case_pass_rate": rate(sum(1 for result in results if result.passed), total_cases),
        "task_completion_rate": rate(completed_cases, total_cases),
        "status_match_rate": rate(status_matches, total_cases),
        "average_tool_call_count": round(sum(result.tool_call_count for result in results) / total_cases, 4) if total_cases else 0.0,
        "human_escalation_ratio": rate(human_escalations, total_cases),
        "rag_evidence_coverage": rate(sum(1 for result in rag_cases if result.evidence_count > 0), len(rag_cases)),
        "continuation_success_rate": rate(
            sum(1 for result in continuation_cases if result.continuation_success),
            len(continuation_cases),
        ),
        "failure_type_distribution": failure_distribution,
        "results": [result.as_dict() for result in results],
        "notes": [
            "Metrics are from fixed offline eval cases only.",
            "Evaluation uses a fake registry and does not require the real Go service.",
            "LLM is disabled for offline evaluation; no vector database, full MCP Server, or new ticket type is used.",
        ],
    }
    return summary


def rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


FAILURE_CATEGORIES = [
    "no_evidence",
    "tool_failure",
    "missing_parameters",
    "expected_balance_mismatch",
    "internal_reconciliation_mismatch",
    "invalid_expected_balance",
    "unsupported_scope",
    "status_mismatch",
    "type_mismatch",
]
