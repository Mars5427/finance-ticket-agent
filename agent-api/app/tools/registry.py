from __future__ import annotations

import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from app.tools.go_client import GoAPIError, GoAccountClient

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolCallResult:
    name: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    status: str
    elapsed_ms: int
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: ToolHandler

    def run(self, tool_input: dict[str, Any]) -> ToolCallResult:
        started = perf_counter()
        try:
            self._validate_required(tool_input)
            output = self.handler(tool_input)
            return ToolCallResult(
                name=self.name,
                input=tool_input,
                output=output,
                status="succeeded",
                elapsed_ms=int((perf_counter() - started) * 1000),
            )
        except GoAPIError as exc:
            return ToolCallResult(
                name=self.name,
                input=tool_input,
                output={"code": exc.code, "status_code": exc.status_code, "payload": exc.payload},
                status="failed",
                elapsed_ms=int((perf_counter() - started) * 1000),
                error=exc.message,
            )
        except Exception as exc:
            return ToolCallResult(
                name=self.name,
                input=tool_input,
                output={"code": "TOOL_ERROR"},
                status="failed",
                elapsed_ms=int((perf_counter() - started) * 1000),
                error=str(exc),
            )

    def _validate_required(self, tool_input: dict[str, Any]) -> None:
        required = self.input_schema.get("required", [])
        missing = [field for field in required if field not in tool_input]
        if missing:
            raise ValueError(f"missing required tool input fields: {', '.join(missing)}")


class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
            for tool in self._tools.values()
        ]

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"tool not registered: {name}")
        return self._tools[name]

    def run(self, name: str, tool_input: dict[str, Any]) -> ToolCallResult:
        return self.get(name).run(tool_input)


def build_default_registry() -> ToolRegistry:
    client = GoAccountClient(
        base_url=os.getenv("GO_ACCOUNT_API_BASE_URL", "http://127.0.0.1:8080"),
        timeout_seconds=float(os.getenv("GO_ACCOUNT_API_TIMEOUT_SECONDS", "5")),
    )
    return build_registry(client)


def build_registry(client: GoAccountClient) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="get_account",
                description="Fetch account summary data from the Go account transaction service.",
                input_schema={
                    "type": "object",
                    "required": ["account_id"],
                    "properties": {"account_id": {"type": "string", "description": "Go account UUID"}},
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "currency": {"type": "string"},
                        "balance": {"type": "integer"},
                        "created_at": {"type": "string"},
                    },
                },
                handler=lambda payload: client.get_account(str(payload["account_id"])),
            ),
            ToolDefinition(
                name="list_account_transactions",
                description="Fetch account ledger entries from the Go account transaction service.",
                input_schema={
                    "type": "object",
                    "required": ["account_id"],
                    "properties": {
                        "account_id": {"type": "string", "description": "Go account UUID"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "entries": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer"},
                                    "transfer_id": {"type": "string"},
                                    "account_id": {"type": "string"},
                                    "direction": {"type": "string"},
                                    "amount": {"type": "integer"},
                                    "balance_after": {"type": "integer"},
                                    "created_at": {"type": "string"},
                                },
                            },
                        }
                    },
                },
                handler=lambda payload: client.list_account_transactions(
                    str(payload["account_id"]),
                    int(payload.get("limit", 50)),
                ),
            ),
            ToolDefinition(
                name="get_transaction_detail",
                description="Fetch transfer details by transfer id from the Go account transaction service.",
                input_schema={
                    "type": "object",
                    "required": ["transfer_id"],
                    "properties": {"transfer_id": {"type": "string", "description": "Go transfer UUID"}},
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                        "from_account_id": {"type": "string"},
                        "to_account_id": {"type": "string"},
                        "amount": {"type": "integer"},
                        "currency": {"type": "string"},
                        "status": {"type": "string"},
                        "created_at": {"type": "string"},
                        "completed_at": {"type": "string"},
                    },
                },
                handler=lambda payload: client.get_transaction_detail(str(payload["transfer_id"])),
            ),
            ToolDefinition(
                name="check_account_reconciliation",
                description="Check whether Go account balance matches the latest ledger balance_after.",
                input_schema={
                    "type": "object",
                    "required": ["account_id"],
                    "properties": {"account_id": {"type": "string", "description": "Go account UUID"}},
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string"},
                        "current_balance": {"type": "integer"},
                        "latest_ledger_balance_after": {"type": ["integer", "null"]},
                        "matched": {"type": "boolean"},
                        "issues": {"type": "array", "items": {"type": "string"}},
                    },
                },
                handler=lambda payload: client.check_account_reconciliation(str(payload["account_id"])),
            ),
        ]
    )
