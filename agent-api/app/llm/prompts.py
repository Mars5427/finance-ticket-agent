from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "finance_ticket_summary_v1"


def build_summary_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    compact_context = {
        "prompt_version": PROMPT_VERSION,
        "ticket_type": context.get("ticket_type"),
        "title": context.get("title"),
        "description": context.get("description"),
        "metadata": context.get("metadata", {}),
        "deterministic_summary": context.get("deterministic_summary"),
        "evidence": _compact_evidence(context.get("evidence", [])),
        "tool_calls": _compact_tool_calls(context.get("tool_calls", [])),
        "needs_human": context.get("needs_human", False),
        "escalation_reason": context.get("escalation_reason"),
    }
    system_prompt = (
        "You are a finance ticket summary refiner. "
        "Use only the provided RAG evidence snippets and tool outputs. "
        "Do not invent reimbursement rules, approval standards, balances, ledger entries, or transactions. "
        "If evidence is insufficient, state the limitation. "
        "If needs_human is true, preserve the human review recommendation. "
        "Never cancel a human escalation that the deterministic workflow already requires. "
        "Return JSON only with keys: summary, needs_human, escalation_reason, confidence. "
        "confidence must be one of low, medium, high. "
        'Example JSON output: {"summary":"Based on the provided evidence and tool outputs, ...","needs_human":true,"escalation_reason":"Manual review is required because ...","confidence":"medium"}.'
    )
    user_prompt = json.dumps(compact_context, ensure_ascii=False, default=str)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _compact_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": item.get("source"),
            "heading": item.get("heading"),
            "snippet": item.get("snippet"),
            "score": item.get("score"),
            "chunk_id": item.get("chunk_id"),
        }
        for item in evidence[:5]
    ]


def _compact_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact_calls = []
    for call in tool_calls:
        compact_calls.append(
            {
                "name": call.get("name"),
                "input": call.get("input"),
                "output": call.get("output"),
                "status": call.get("status"),
                "error": call.get("error"),
            }
        )
    return compact_calls
