import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type TicketStatus = "completed" | "needs_more_info" | "escalated" | "failed";

type TraceEvent = {
  id: string;
  step: string;
  event_type: string;
  payload: Record<string, unknown>;
  elapsed_ms: number;
  error: string | null;
  created_at: string;
};

type Ticket = {
  id: string;
  title: string;
  description: string;
  type: string;
  status: TicketStatus;
  metadata: Record<string, unknown>;
  dialogue_context: Array<Record<string, unknown>>;
  result: {
    summary: string;
    evidence: Array<Record<string, unknown>>;
    tool_calls: Array<Record<string, unknown>>;
    needs_human: boolean;
    escalation_reason: string | null;
    follow_up_question: string | null;
  };
  trace: TraceEvent[];
  created_at: string;
  updated_at: string;
};

const examples = [
  {
    label: "报销规则",
    title: "出差餐补报销规则",
    description: "我下周去上海出差，想问餐补需要哪些材料？",
    metadata: {}
  },
  {
    label: "余额异常",
    title: "余额异常解释",
    description: "账户余额比我预期少 500，帮我解释一下。",
    metadata: { account_id: "demo-account", observed_balance: 1500 }
  },
  {
    label: "对账异常",
    title: "本月对账差异",
    description: "这个账户本月对账差了 1000，帮我定位原因。",
    metadata: { account_id: "demo-account", expected_balance: 3000, time_range: "2026-08" }
  }
];

function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState(examples[0].title);
  const [description, setDescription] = useState(examples[0].description);
  const [metadata, setMetadata] = useState(JSON.stringify(examples[0].metadata, null, 2));
  const [error, setError] = useState<string | null>(null);
  const selected = useMemo(() => tickets.find((ticket) => ticket.id === selectedId) ?? tickets[0], [tickets, selectedId]);

  async function loadTickets() {
    const response = await fetch("/api/tickets");
    if (!response.ok) {
      throw new Error("工单列表加载失败");
    }
    const data = (await response.json()) as Ticket[];
    setTickets(data);
    if (!selectedId && data.length > 0) {
      setSelectedId(data[0].id);
    }
  }

  useEffect(() => {
    loadTickets().catch((err: Error) => setError(err.message));
  }, []);

  async function createTicket(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    let parsedMetadata: Record<string, unknown>;
    try {
      parsedMetadata = JSON.parse(metadata) as Record<string, unknown>;
    } catch {
      setError("metadata 必须是合法 JSON 对象");
      return;
    }

    const response = await fetch("/api/tickets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description, metadata: parsedMetadata })
    });

    if (!response.ok) {
      setError("工单创建失败");
      return;
    }

    const ticket = (await response.json()) as Ticket;
    setTickets((current) => [ticket, ...current]);
    setSelectedId(ticket.id);
  }

  function applyExample(index: number) {
    const example = examples[index];
    setTitle(example.title);
    setDescription(example.description);
    setMetadata(JSON.stringify(example.metadata, null, 2));
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1>面向财务场景的智能工单处理 Agent</h1>
          <p>Deterministic workflow by default, optional LLM summary when configured</p>
        </div>
        <StatusLegend />
      </header>

      <section className="layout">
        <aside className="sidebar">
          <form className="composer" onSubmit={createTicket}>
            <div className="example-row">
              {examples.map((example, index) => (
                <button key={example.label} type="button" onClick={() => applyExample(index)}>
                  {example.label}
                </button>
              ))}
            </div>
            <label>
              标题
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label>
              描述
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} />
            </label>
            <label>
              metadata JSON
              <textarea value={metadata} onChange={(event) => setMetadata(event.target.value)} rows={6} className="mono" />
            </label>
            <button className="primary" type="submit">
              创建工单
            </button>
            {error ? <p className="error">{error}</p> : null}
          </form>

          <div className="ticket-list">
            <h2>工单列表</h2>
            {tickets.length === 0 ? <p className="empty">暂无工单。请先启动 FastAPI 并创建工单。</p> : null}
            {tickets.map((ticket) => (
              <button
                className={`ticket-item ${ticket.id === selected?.id ? "active" : ""}`}
                key={ticket.id}
                type="button"
                onClick={() => setSelectedId(ticket.id)}
              >
                <span>{ticket.title}</span>
                <StatusBadge status={ticket.status} />
              </button>
            ))}
          </div>
        </aside>

        <section className="detail">
          {selected ? <TicketDetail ticket={selected} onTicketUpdated={(ticket) => setTickets((current) => current.map((item) => (item.id === ticket.id ? ticket : item)))} /> : <EmptyDetail />}
        </section>
      </section>
    </main>
  );
}

function TicketDetail({ ticket, onTicketUpdated }: { ticket: Ticket; onTicketUpdated: (ticket: Ticket) => void }) {
  return (
    <>
      <div className="detail-head">
        <div>
          <p className="eyebrow">{ticket.type}</p>
          <h2>{ticket.title}</h2>
          <p>{ticket.description}</p>
        </div>
        <StatusBadge status={ticket.status} />
      </div>

      <section className="panel">
        <h3>处理结论</h3>
        <p>{ticket.result.summary}</p>
        {ticket.result.follow_up_question ? <p className="notice">{ticket.result.follow_up_question}</p> : null}
        {ticket.result.escalation_reason ? <p className="notice">{ticket.result.escalation_reason}</p> : null}
      </section>

      {ticket.status === "needs_more_info" ? <ContinueTicketForm key={ticket.id} ticket={ticket} onTicketUpdated={onTicketUpdated} /> : null}

      <section className="split">
        <div className="panel">
          <h3>工具调用</h3>
          {ticket.result.tool_calls.length === 0 ? <p className="muted">当前工单未执行业务工具。</p> : null}
          {ticket.result.tool_calls.map((call, index) => (
            <pre key={index}>{JSON.stringify(call, null, 2)}</pre>
          ))}
        </div>
        <div className="panel">
          <h3>依据片段</h3>
          {ticket.result.evidence.length === 0 ? <p className="muted">当前工单暂无依据片段。</p> : null}
          {ticket.result.evidence.map((item, index) => (
            <pre key={index}>{JSON.stringify(item, null, 2)}</pre>
          ))}
        </div>
      </section>

      <section className="panel">
        <h3>执行步骤</h3>
        <ol className="trace">
          {ticket.trace.map((event) => (
            <li key={event.id}>
              <div className="trace-main">
                <strong>{event.step}</strong>
                <span>{event.event_type}</span>
                <small>{event.elapsed_ms} ms</small>
              </div>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

function ContinueTicketForm({ ticket, onTicketUpdated }: { ticket: Ticket; onTicketUpdated: (ticket: Ticket) => void }) {
  const [message, setMessage] = useState("");
  const [metadataPatch, setMetadataPatch] = useState(defaultMetadataPatch(ticket));
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    let parsedPatch: Record<string, unknown>;
    try {
      parsedPatch = JSON.parse(metadataPatch) as Record<string, unknown>;
      if (!parsedPatch || Array.isArray(parsedPatch) || typeof parsedPatch !== "object") {
        throw new Error("metadata_patch 必须是 JSON 对象");
      }
    } catch {
      setError("metadata_patch 必须是合法 JSON 对象");
      return;
    }

    const response = await fetch(`/api/tickets/${ticket.id}/continue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, metadata_patch: parsedPatch })
    });

    if (!response.ok) {
      setError("补充信息提交失败");
      return;
    }

    const updated = (await response.json()) as Ticket;
    onTicketUpdated(updated);
  }

  return (
    <section className="panel">
      <h3>补充信息</h3>
      <form className="continue-form" onSubmit={submit}>
        <label>
          回复
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={3} />
        </label>
        <label>
          metadata_patch JSON
          <textarea value={metadataPatch} onChange={(event) => setMetadataPatch(event.target.value)} rows={5} className="mono" />
        </label>
        <button className="primary" type="submit">
          继续处理
        </button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </section>
  );
}

function defaultMetadataPatch(ticket: Ticket) {
  if (ticket.type === "balance_anomaly") {
    return JSON.stringify({ account_id: "demo-account", observed_balance: 1500 }, null, 2);
  }
  if (ticket.type === "reconciliation_anomaly") {
    return JSON.stringify({ account_id: "demo-account", expected_balance: 1500, time_range: "2026-08" }, null, 2);
  }
  return JSON.stringify({}, null, 2);
}

function EmptyDetail() {
  return (
    <div className="empty-detail">
      <h2>等待工单</h2>
      <p>启动 FastAPI 后，创建一个报销、余额或对账工单即可查看执行 trace。</p>
    </div>
  );
}

function StatusBadge({ status }: { status: TicketStatus }) {
  return <span className={`status ${status}`}>{status}</span>;
}

function StatusLegend() {
  return (
    <div className="legend">
      <StatusBadge status="completed" />
      <StatusBadge status="needs_more_info" />
      <StatusBadge status="escalated" />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
