from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import TicketContinueRequest, TicketCreateRequest, TicketResponse, TraceEvent
from app.store import store
from app.tools import build_default_registry
from app.workflow import run_agent_workflow

app = FastAPI(title="Finance Ticket Agent API", version="0.1.0")
tool_registry = build_default_registry()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/tickets", response_model=TicketResponse)
def create_ticket(request: TicketCreateRequest) -> TicketResponse:
    ticket = run_agent_workflow(request, registry=tool_registry)
    store.save(ticket)
    return ticket


@app.get("/api/tickets", response_model=list[TicketResponse])
def list_tickets() -> list[TicketResponse]:
    return store.list()


@app.get("/api/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: str) -> TicketResponse:
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ticket


@app.get("/api/tickets/{ticket_id}/trace", response_model=list[TraceEvent])
def get_ticket_trace(ticket_id: str) -> list[TraceEvent]:
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ticket.trace


@app.post("/api/tickets/{ticket_id}/continue", response_model=TicketResponse)
def continue_ticket(ticket_id: str, request: TicketContinueRequest) -> TicketResponse:
    existing = store.get(ticket_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    if existing.status != "needs_more_info":
        raise HTTPException(status_code=409, detail="only needs_more_info tickets can be continued in Phase 4.5")

    merged_metadata = {**existing.metadata, **request.metadata_patch}
    rerun_request = TicketCreateRequest(
        title=existing.title,
        description=existing.description,
        metadata=merged_metadata,
    )
    ticket = run_agent_workflow(
        rerun_request,
        registry=tool_registry,
        ticket_id=existing.id,
        prior_dialogue_context=existing.dialogue_context,
        prior_trace=existing.trace,
        continuation_message=request.message,
        metadata_patch=request.metadata_patch,
        created_at=existing.created_at,
    )
    store.save(ticket)
    return ticket


@app.get("/api/tools")
def list_tools() -> list[dict[str, object]]:
    return tool_registry.list_tools()
