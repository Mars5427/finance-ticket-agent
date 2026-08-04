# agent-api

Python FastAPI service for the finance ticket Agent.

Current Phase 6.5 status:
- optional LLM summary refinement is available
- default configuration disables LLM and keeps deterministic fallback
- LangGraph workflow is active
- Markdown RAG is active
- MCP-style Tool Registry calls the Go HTTP API
- lightweight same-ticket continuation is supported only for missing-parameter tickets
- offline fixed-case evaluation is available from `scripts\run_eval.py`
- in-memory ticket, dialogue_context, and trace store

Optional LLM config:

```powershell
$env:LLM_ENABLED="true"
$env:LLM_PROVIDER="deepseek"
$env:LLM_API_KEY="<redacted>"
$env:LLM_MODEL="deepseek-v4-flash"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_TIMEOUT_SECONDS="20"
$env:LLM_MAX_TOKENS="800"
```

Without these variables the workflow records `llm_skipped` and remains fully local.

Run:

```powershell
cd D:\finance-ticket-agent\agent-api
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Test:

```powershell
cd D:\finance-ticket-agent\agent-api
python -m unittest discover -s tests -v
```

Evaluate:

```powershell
cd D:\finance-ticket-agent\agent-api
python scripts\run_eval.py
```
