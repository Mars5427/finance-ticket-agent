from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.llm import LLMClientProtocol, LLMConfig, OpenAICompatibleLLMClient, PROMPT_VERSION, build_summary_messages, get_llm_config
from app.models import TicketCreateRequest, TicketResponse, TicketResult, TraceEvent, TicketType, new_id, utc_now
from app.rag import retrieve_evidence as retrieve_knowledge_evidence
from app.tools import ToolRegistry, build_default_registry


class WorkflowState(TypedDict, total=False):
    request: TicketCreateRequest
    registry: ToolRegistry
    llm_config: LLMConfig
    llm_client: LLMClientProtocol | None
    started: float
    ticket_id: str
    context: dict[str, Any]
    ticket_type: TicketType
    status: str
    missing_fields: list[str]
    follow_up_question: str | None
    plan: list[str]
    candidate_tools: list[str]
    tool_calls: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    rag_meta: dict[str, Any]
    summary: str
    needs_human: bool
    escalation_reason: str | None
    llm_confidence: str | None
    ticket_response: TicketResponse
    trace: list[TraceEvent]
    prior_trace: list[TraceEvent]
    prior_dialogue_context: list[dict[str, Any]]
    continuation_message: str | None
    metadata_patch: dict[str, Any]
    created_at: Any


Route = Literal["ready", "needs_more_info", "unsupported"]


def run_agent_workflow(
    request: TicketCreateRequest,
    registry: ToolRegistry | None = None,
    ticket_id: str | None = None,
    prior_dialogue_context: list[dict[str, Any]] | None = None,
    prior_trace: list[TraceEvent] | None = None,
    continuation_message: str | None = None,
    metadata_patch: dict[str, Any] | None = None,
    created_at: Any = None,
    llm_config: LLMConfig | None = None,
    llm_client: LLMClientProtocol | None = None,
) -> TicketResponse:
    app = build_langgraph_workflow()
    final_state = app.invoke(
        {
            "request": request,
            "registry": registry or build_default_registry(),
            "started": perf_counter(),
            "ticket_id": ticket_id,
            "prior_dialogue_context": prior_dialogue_context or [],
            "prior_trace": prior_trace or [],
            "continuation_message": continuation_message,
            "metadata_patch": metadata_patch or {},
            "created_at": created_at,
            "llm_config": llm_config or get_llm_config(),
            "llm_client": llm_client,
        }
    )
    return final_state["ticket_response"]


def run_deterministic_workflow(request: TicketCreateRequest, registry: ToolRegistry | None = None) -> TicketResponse:
    return run_agent_workflow(request, registry=registry)


def build_langgraph_workflow():
    graph = StateGraph(WorkflowState)
    graph.add_node("initialize_context", initialize_context)
    graph.add_node("classify", classify)
    graph.add_node("check_missing_fields", check_missing_fields)
    graph.add_node("plan", plan)
    graph.add_node("retrieve_evidence", retrieve_evidence)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("summarize", summarize)
    graph.add_node("llm_summarize", llm_summarize)
    graph.add_node("escalation_check", escalation_check)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("initialize_context")
    graph.add_edge("initialize_context", "classify")
    graph.add_edge("classify", "check_missing_fields")
    graph.add_conditional_edges(
        "check_missing_fields",
        route_after_missing_check,
        {
            "ready": "plan",
            "needs_more_info": "summarize",
            "unsupported": "summarize",
        },
    )
    graph.add_edge("plan", "retrieve_evidence")
    graph.add_edge("retrieve_evidence", "execute_tools")
    graph.add_edge("execute_tools", "summarize")
    graph.add_edge("summarize", "llm_summarize")
    graph.add_edge("llm_summarize", "escalation_check")
    graph.add_edge("escalation_check", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def initialize_context(state: WorkflowState) -> WorkflowState:
    request = state["request"]
    started = state["started"]
    trace: list[TraceEvent] = list(state.get("prior_trace", []))
    ticket_id = state.get("ticket_id") or new_id("ticket")
    prior_dialogue = list(state.get("prior_dialogue_context", []))
    is_continuation = bool(state.get("continuation_message"))
    dialogue_context = prior_dialogue or [{"role": "user", "content": f"{request.title}\n{request.description}", "kind": "initial_ticket"}]
    if is_continuation:
        trace.append(
            _event(
                "continue_ticket",
                "continue_ticket",
                {"ticket_id": ticket_id, "message": state.get("continuation_message")},
                started,
            )
        )
        trace.append(
            _event(
                "metadata_patch_applied",
                "metadata_patch_applied",
                {"metadata_patch": state.get("metadata_patch", {}), "merged_metadata": request.metadata},
                started,
            )
        )
        dialogue_context.append({"role": "user", "content": state.get("continuation_message"), "kind": "metadata_follow_up"})
        trace.append(
            _event(
                "dialogue_context_updated",
                "dialogue_context_updated",
                {"dialogue_turn_count": len(dialogue_context)},
                started,
            )
        )
    context = {
        "ticket_id": ticket_id,
        "title": request.title,
        "description": request.description,
        "metadata": request.metadata,
        "dialogue_context": dialogue_context,
        "tool_history": [],
    }
    trace.append(_event("initialize_context", "workflow_node", {"ticket_id": ticket_id, "is_continuation": is_continuation}, started))
    return {
        **state,
        "ticket_id": ticket_id,
        "context": context,
        "trace": trace,
        "tool_calls": [],
        "evidence": [],
        "rag_meta": {},
        "needs_human": False,
        "escalation_reason": None,
        "follow_up_question": None,
    }


def classify(state: WorkflowState) -> WorkflowState:
    request = state["request"]
    ticket_type = classify_ticket(request)
    _append_trace(
        state,
        "classify",
        "classification",
        {"ticket_type": ticket_type, "strategy": "deterministic_keywords_in_langgraph_node"},
    )
    return {**state, "ticket_type": ticket_type}


def check_missing_fields(state: WorkflowState) -> WorkflowState:
    ticket_type = state["ticket_type"]
    missing = required_missing_fields(ticket_type, state["request"].metadata)
    question = follow_up_question(ticket_type, missing) if missing else None
    _append_trace(
        state,
        "check_missing_fields",
        "missing_parameters",
        {"missing_fields": missing, "follow_up_question": question},
    )
    return {**state, "missing_fields": missing, "follow_up_question": question}


def route_after_missing_check(state: WorkflowState) -> Route:
    if state["ticket_type"] == "unsupported":
        return "unsupported"
    if state.get("missing_fields"):
        return "needs_more_info"
    return "ready"


def plan(state: WorkflowState) -> WorkflowState:
    ticket_type = state["ticket_type"]
    steps = task_plan(ticket_type)
    tools = candidate_tools(ticket_type)
    _append_trace(state, "plan", "task_decomposition", {"steps": steps, "candidate_tools": tools})
    return {**state, "plan": steps, "candidate_tools": tools}


def retrieve_evidence(state: WorkflowState) -> WorkflowState:
    ticket_type = state["ticket_type"]
    request = state["request"]
    query = rag_query(ticket_type, request)
    sources = rag_sources(ticket_type)
    evidence, meta = retrieve_knowledge_evidence(query, sources=sources, top_k=3, min_score=rag_min_score(ticket_type))
    _append_trace(
        state,
        "retrieve_evidence",
        "rag_retrieval",
        {
            "query": meta["query"],
            "matched_sources": meta["matched_sources"],
            "snippets": meta["snippets"],
            "scores": meta["scores"],
            "elapsed_ms": meta["elapsed_ms"],
            "no_evidence_reason": meta["no_evidence_reason"],
        },
    )
    return {**state, "evidence": evidence, "rag_meta": meta}


def execute_tools(state: WorkflowState) -> WorkflowState:
    ticket_type = state["ticket_type"]
    request = state["request"]
    registry = state["registry"]
    tool_calls: list[dict[str, Any]] = []

    if ticket_type == "balance_anomaly":
        account_id = request.metadata["account_id"]
        account_call = registry.run("get_account", {"account_id": account_id})
        ledger_call = registry.run("list_account_transactions", {"account_id": account_id, "limit": 50})
        tool_calls.extend([account_call.as_dict(), ledger_call.as_dict()])
        detail_call = first_transfer_detail_call(registry, ledger_call.output)
        if detail_call is not None:
            tool_calls.append(detail_call.as_dict())
    elif ticket_type == "reconciliation_anomaly":
        account_id = request.metadata["account_id"]
        ledger_call = registry.run("list_account_transactions", {"account_id": account_id, "limit": 50})
        reconciliation_call = registry.run("check_account_reconciliation", {"account_id": account_id})
        tool_calls.extend([ledger_call.as_dict(), reconciliation_call.as_dict()])

    state["context"]["tool_history"] = tool_calls
    for event in tool_trace_events(tool_calls, state["started"]):
        state["trace"].append(event)
    return {**state, "tool_calls": tool_calls}


def summarize(state: WorkflowState) -> WorkflowState:
    ticket_type = state["ticket_type"]
    request = state["request"]
    tool_calls = state.get("tool_calls", [])
    failed = [call for call in tool_calls if call["status"] != "succeeded"]
    evidence = state.get("evidence", [])
    rag_meta = state.get("rag_meta", {})
    summary = ""
    needs_human = False
    escalation_reason: str | None = None

    if state.get("missing_fields"):
        summary = "需要补充信息后才能继续处理。"
        status = "needs_more_info"
    elif ticket_type == "unsupported":
        summary = "当前 MVP 只支持报销规则问答、余额异常解释、对账异常定位三类财务工单。"
        needs_human = True
        escalation_reason = summary
        status = "escalated"
    elif ticket_type == "reimbursement_policy":
        if evidence:
            summary = build_reimbursement_summary(evidence)
        else:
            summary = "知识库未检索到足够依据，无法可靠回答该报销规则问题，建议人工确认制度口径。"
            needs_human = True
            escalation_reason = rag_meta.get("no_evidence_reason") or "No reimbursement policy evidence found."
        status = needs_human and "escalated" or "completed"
    elif failed:
        summary = tool_failure_summary(ticket_type)
        needs_human = True
        escalation_reason = tool_failure_reason(ticket_type)
        status = "escalated"
    elif ticket_type == "balance_anomaly":
        account_output = tool_output(tool_calls, "get_account")
        ledger_entries = tool_output(tool_calls, "list_account_transactions").get("entries", [])
        summary = build_balance_summary(account_output, ledger_entries, request.metadata["observed_balance"])
        if evidence:
            summary += f" 异常处理依据：{format_evidence_hint(evidence)}"
        elif rag_meta.get("no_evidence_reason"):
            summary += " 知识库未检索到强相关异常处理依据，未额外补充 SOP 结论。"
        status = "completed"
    elif ticket_type == "reconciliation_anomaly":
        expected_balance = parse_int(request.metadata.get("expected_balance"))
        if expected_balance is None:
            summary = "对账异常定位需要整数格式的 expected_balance；当前字段无法转换为整数，已升级人工确认。"
            needs_human = True
            escalation_reason = "metadata.expected_balance is not a valid integer."
        else:
            decision = build_reconciliation_decision(tool_output(tool_calls, "check_account_reconciliation"), expected_balance)
            summary = decision["summary"]
            needs_human = decision["needs_human"]
            escalation_reason = decision["escalation_reason"]
            if evidence:
                summary += f" 对账 SOP 依据：{format_evidence_hint(evidence)}"
            else:
                summary += " 知识库未检索到足够 SOP 依据，人工复核建议仅基于工具返回和输入差异。"
        status = needs_human and "escalated" or "completed"
    else:
        summary = "Unsupported ticket."
        needs_human = True
        escalation_reason = "Unsupported ticket type."
        status = "escalated"

    _append_trace(
        state,
        "summarize",
        "structured_output",
        {
            "status": status,
            "summary": summary,
            "tool_call_count": len(tool_calls),
            "evidence_count": len(evidence),
            "escalation_reason": escalation_reason,
        },
    )
    return {
        **state,
        "summary": summary,
        "evidence": evidence,
        "needs_human": needs_human,
        "escalation_reason": escalation_reason,
        "status": status,
    }


def llm_summarize(state: WorkflowState) -> WorkflowState:
    config = state.get("llm_config") or get_llm_config()
    if not config.available:
        _append_trace(
            state,
            "llm_summarize",
            "llm_skipped",
            {
                "provider": config.provider,
                "model": config.model,
                "prompt_version": PROMPT_VERSION,
                "reason": config.skip_reason,
            },
        )
        return state

    messages = build_summary_messages(
        {
            "ticket_type": state.get("ticket_type"),
            "title": state["request"].title,
            "description": state["request"].description,
            "metadata": state["request"].metadata,
            "deterministic_summary": state.get("summary"),
            "evidence": state.get("evidence", []),
            "tool_calls": state.get("tool_calls", []),
            "needs_human": state.get("needs_human", False),
            "escalation_reason": state.get("escalation_reason"),
        }
    )
    client = state.get("llm_client") or OpenAICompatibleLLMClient()
    original_summary = state.get("summary", "")
    original_needs_human = bool(state.get("needs_human", False))
    original_escalation_reason = state.get("escalation_reason")
    try:
        completion = client.complete_json(messages, config)
        parsed = parse_llm_summary(completion.content)
    except Exception as exc:
        _append_trace(
            state,
            "llm_summarize",
            "llm_fallback",
            {
                "provider": config.provider,
                "model": config.model,
                "prompt_version": PROMPT_VERSION,
                "error": str(exc),
                "fallback_reason": "Keep deterministic summary because LLM request or output validation failed.",
            },
        )
        return {
            **state,
            "summary": original_summary,
            "needs_human": original_needs_human,
            "escalation_reason": original_escalation_reason,
        }

    refined_summary = parsed["summary"]
    model_needs_human = bool(parsed["needs_human"])
    needs_human = original_needs_human or model_needs_human
    escalation_reason = merge_escalation_reason(original_needs_human, original_escalation_reason, model_needs_human, parsed.get("escalation_reason"))
    _append_trace(
        state,
        "llm_summarize",
        "llm_call",
        {
            "provider": config.provider,
            "model": config.model,
            "prompt_version": PROMPT_VERSION,
            "elapsed_ms": completion.elapsed_ms,
            "input_summary_length": len(original_summary),
            "output_summary_length": len(refined_summary),
            "confidence": parsed["confidence"],
        },
    )
    return {
        **state,
        "summary": refined_summary,
        "needs_human": needs_human,
        "escalation_reason": escalation_reason,
        "llm_confidence": parsed["confidence"],
    }


def escalation_check(state: WorkflowState) -> WorkflowState:
    status = state.get("status", "completed")
    needs_human = bool(state.get("needs_human", False))
    if state.get("missing_fields"):
        status = "needs_more_info"
        needs_human = False
    elif needs_human:
        status = "escalated"
    _append_trace(
        state,
        "escalation_check",
        "human_escalation",
        {
            "status": status,
            "needs_human": needs_human,
            "reason": state.get("escalation_reason"),
        },
    )
    return {**state, "status": status, "needs_human": needs_human}


def finalize(state: WorkflowState) -> WorkflowState:
    _append_trace(
        state,
        "finalize",
        "ticket_finalized",
        {"ticket_id": state["ticket_id"], "status": state["status"], "ticket_type": state["ticket_type"]},
    )
    request = state["request"]
    result = TicketResult(
        summary=state["summary"],
        evidence=state.get("evidence", []),
        tool_calls=state.get("tool_calls", []),
        needs_human=state.get("needs_human", False),
        escalation_reason=state.get("escalation_reason"),
        follow_up_question=state.get("follow_up_question"),
    )
    ticket = TicketResponse(
        id=state["ticket_id"],
        title=request.title,
        description=request.description,
        type=state["ticket_type"],
        status=state["status"],
        metadata=request.metadata,
        dialogue_context=state["context"].get("dialogue_context", []),
        result=result,
        trace=state["trace"],
        created_at=state.get("created_at") or utc_now(),
        updated_at=utc_now(),
    )
    return {**state, "ticket_response": ticket}


def classify_ticket(request: TicketCreateRequest) -> TicketType:
    text = f"{request.title} {request.description}".lower()
    if any(keyword in text for keyword in ["报销", "发票", "餐补", "住宿", "差旅", "审批", "reimbursement", "expense", "invoice", "travel", "meal", "approval"]):
        return "reimbursement_policy"
    if any(keyword in text for keyword in ["对账", "差异", "reconciliation", "核验"]):
        return "reconciliation_anomaly"
    if any(keyword in text for keyword in ["余额", "少了", "多了", "balance"]):
        return "balance_anomaly"
    return "unsupported"


def required_missing_fields(ticket_type: TicketType, metadata: dict[str, Any]) -> list[str]:
    required_by_type: dict[str, list[str]] = {
        "balance_anomaly": ["account_id", "observed_balance"],
        "reconciliation_anomaly": ["account_id", "expected_balance", "time_range"],
    }
    return [field for field in required_by_type.get(ticket_type, []) if field not in metadata]


def follow_up_question(ticket_type: TicketType, missing: list[str]) -> str:
    label = {
        "account_id": "账户 ID",
        "observed_balance": "你看到的余额",
        "expected_balance": "对账单或预期余额",
        "time_range": "对账时间范围",
    }
    missing_text = "、".join(label.get(item, item) for item in missing)
    if ticket_type == "balance_anomaly":
        return f"为了解释余额异常，请补充：{missing_text}。"
    if ticket_type == "reconciliation_anomaly":
        return f"为了定位对账异常，请补充：{missing_text}。"
    return f"请补充：{missing_text}。"


def task_plan(ticket_type: TicketType) -> list[str]:
    plans = {
        "reimbursement_policy": ["检索报销制度，Phase 4 RAG", "检索审批标准，Phase 4 RAG", "汇总依据片段", "判断是否需要人工升级"],
        "balance_anomaly": ["读取账户信息", "读取账户流水", "比较观察余额与账面余额", "汇总差异解释"],
        "reconciliation_anomaly": ["读取账户流水", "执行对账核验", "比较外部 expected_balance", "判断是否需要人工升级"],
    }
    return plans.get(ticket_type, [])


def candidate_tools(ticket_type: TicketType) -> list[str]:
    tools = {
        "reimbursement_policy": [],
        "balance_anomaly": ["get_account", "list_account_transactions", "get_transaction_detail"],
        "reconciliation_anomaly": ["list_account_transactions", "check_account_reconciliation"],
    }
    return tools.get(ticket_type, [])


def rag_sources(ticket_type: TicketType) -> list[str]:
    sources = {
        "reimbursement_policy": ["reimbursement-policy.md", "approval-rules.md"],
        "balance_anomaly": ["reconciliation-sop.md"],
        "reconciliation_anomaly": ["reconciliation-sop.md"],
    }
    return sources.get(ticket_type, [])


def rag_query(ticket_type: TicketType, request: TicketCreateRequest) -> str:
    base = f"{request.title} {request.description}"
    if ticket_type == "reimbursement_policy":
        return f"{base} 报销 发票 餐补 住宿 交通 审批 材料"
    if ticket_type == "reconciliation_anomaly":
        return f"{base} 对账 差异 期望金额 外部对账单 时间范围 缺失流水 入账延迟 升级条件"
    if ticket_type == "balance_anomaly":
        return f"{base} 余额异常 流水 差异 时间范围 入账延迟"
    return base


def rag_min_score(ticket_type: TicketType) -> float:
    if ticket_type == "balance_anomaly":
        return 0.32
    return 0.18


def parse_llm_summary(content: str) -> dict[str, Any]:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be a JSON object.")
    required = {
        "summary": str,
        "needs_human": bool,
        "confidence": str,
    }
    for field, expected_type in required.items():
        if field not in parsed:
            raise ValueError(f"LLM output missing required field: {field}")
        if not isinstance(parsed[field], expected_type):
            raise ValueError(f"LLM output field {field} has invalid type.")
    if "escalation_reason" not in parsed:
        raise ValueError("LLM output missing required field: escalation_reason")
    if parsed["escalation_reason"] is not None and not isinstance(parsed["escalation_reason"], str):
        raise ValueError("LLM output field escalation_reason has invalid type.")
    if parsed["confidence"] not in {"low", "medium", "high"}:
        raise ValueError("LLM output confidence must be low, medium, or high.")
    if not parsed["summary"].strip():
        raise ValueError("LLM output summary cannot be empty.")
    return parsed


def merge_escalation_reason(
    original_needs_human: bool,
    original_reason: str | None,
    model_needs_human: bool,
    model_reason: str | None,
) -> str | None:
    if original_needs_human:
        return original_reason or model_reason or "Deterministic workflow requires human review."
    if model_needs_human:
        return model_reason or "LLM refinement recommends human review based on provided evidence and tool outputs."
    return original_reason


def tool_output(tool_calls: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for call in tool_calls:
        if call.get("name") == name and isinstance(call.get("output"), dict):
            return call["output"]
    return {}


def tool_failure_summary(ticket_type: TicketType) -> str:
    if ticket_type == "balance_anomaly":
        return "余额异常解释需要 Go 业务数据，但至少一个工具调用失败；已记录工具错误并建议人工确认。"
    if ticket_type == "reconciliation_anomaly":
        return "对账异常定位需要 Go 业务数据，但至少一个工具调用失败；已记录工具错误并建议人工确认。"
    return "工具调用失败，已升级人工确认。"


def tool_failure_reason(ticket_type: TicketType) -> str:
    if ticket_type == "balance_anomaly":
        return "Go API tool call failed; check service availability, account id, and tool trace."
    if ticket_type == "reconciliation_anomaly":
        return "Go API reconciliation tool call failed; check service availability and account id."
    return "Tool call failed."


def build_reimbursement_summary(evidence: list[dict[str, Any]]) -> str:
    hints = format_evidence_hint(evidence)
    return f"已从 Markdown 知识库检索到报销制度或审批标准依据：{hints}。请以命中的制度片段为准；如材料缺失、超标准或规则冲突，应进入人工审核。"


def format_evidence_hint(evidence: list[dict[str, Any]]) -> str:
    hints = []
    for item in evidence[:2]:
        hints.append(f"{item.get('source')} / {item.get('heading')}：{item.get('snippet')}")
    return "；".join(hints)


def _event(step: str, event_type: str, payload: dict[str, Any], started: float) -> TraceEvent:
    return TraceEvent(step=step, event_type=event_type, payload=payload, elapsed_ms=int((perf_counter() - started) * 1000))


def _append_trace(state: WorkflowState, step: str, event_type: str, payload: dict[str, Any]) -> None:
    state["trace"].append(_event(step, event_type, payload, state["started"]))


def first_transfer_detail_call(registry: ToolRegistry, ledger_output: dict[str, Any] | None):
    entries = (ledger_output or {}).get("entries", [])
    if not entries:
        return None
    transfer_id = entries[0].get("transfer_id")
    if not transfer_id:
        return None
    return registry.run("get_transaction_detail", {"transfer_id": transfer_id})


def build_balance_summary(account: dict[str, Any], entries: list[dict[str, Any]], observed: Any) -> str:
    balance = account.get("balance")
    delta = None
    try:
        delta = int(observed) - int(balance)
    except Exception:
        pass
    latest = entries[0] if entries else None
    parts = [f"Go 账户服务返回当前账面余额为 {balance}，用户观察余额为 {observed}。"]
    if delta is not None:
        parts.append(f"观察余额与账面余额差值为 {delta}。")
    if latest:
        parts.append(
            f"最新流水方向为 {latest.get('direction')}，金额 {latest.get('amount')}，流水后余额 {latest.get('balance_after')}。"
        )
    else:
        parts.append("该账户当前没有流水记录，无法继续用流水解释差异。")
    return "".join(parts)


def build_reconciliation_summary(reconciliation: dict[str, Any], issues: Any) -> str:
    matched = reconciliation.get("matched")
    current = reconciliation.get("current_balance")
    latest = reconciliation.get("latest_ledger_balance_after")
    if matched:
        return f"Go 对账核验返回 matched=true，账户余额 {current} 与最新流水余额 {latest} 一致或暂无流水差异。issues={issues}。"
    return f"Go 对账核验返回 matched=false，账户余额 {current} 与最新流水余额 {latest} 不一致。issues={issues}，建议人工复核。"


def parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_reconciliation_decision(reconciliation: dict[str, Any], expected_balance: int) -> dict[str, Any]:
    matched = bool(reconciliation.get("matched", False))
    current = reconciliation.get("current_balance")
    latest = reconciliation.get("latest_ledger_balance_after")
    issues = reconciliation.get("issues", [])
    current_int = parse_int(current)
    if current_int is None:
        return {
            "summary": "Go 对账核验返回的 current_balance 无法转换为整数，无法完成对账判断，建议人工复核。",
            "needs_human": True,
            "escalation_reason": "Go reconciliation current_balance is not a valid integer.",
        }

    external_delta = current_int - expected_balance
    if not matched:
        return {
            "summary": build_reconciliation_summary(reconciliation, issues)
            + f" 外部 expected_balance 为 {expected_balance}，与 Go 当前余额差额为 {external_delta}。",
            "needs_human": True,
            "escalation_reason": "Go reconciliation returned internal ledger mismatch issues.",
        }
    if external_delta != 0:
        return {
            "summary": (
                f"Go 内部账户与流水一致：current_balance={current_int}，latest_ledger_balance_after={latest}，issues={issues}。"
                f"但外部对账单或用户预期余额 expected_balance={expected_balance}，与当前余额差额为 {external_delta}。"
                "建议人工复核外部对账单来源、时间范围或入账延迟。"
            ),
            "needs_human": True,
            "escalation_reason": (
                "Go internal balance and ledger are matched, but expected_balance differs from current_balance "
                f"by {external_delta}; review external statement source, time range, or posting delay."
            ),
        }
    return {
        "summary": (
            f"Go 内部账户与流水一致：current_balance={current_int}，latest_ledger_balance_after={latest}，issues={issues}。"
            f"外部 expected_balance={expected_balance} 也与当前余额一致，暂未发现对账差异。"
        ),
        "needs_human": False,
        "escalation_reason": None,
    }


def tool_trace_events(tool_calls: list[dict[str, Any]], started: float) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for call in tool_calls:
        events.append(
            _event(
                "execute_tools",
                "tool_call",
                {
                    "tool_name": call.get("name"),
                    "input": call.get("input"),
                    "output": call.get("output"),
                    "status": call.get("status"),
                    "elapsed_ms": call.get("elapsed_ms"),
                    "error": call.get("error"),
                },
                started,
            )
        )
    return events
