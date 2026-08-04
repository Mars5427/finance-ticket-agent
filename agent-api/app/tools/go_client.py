from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class GoAPIError(Exception):
    status_code: int | None
    code: str
    message: str
    payload: dict[str, Any] | None = None


class GoAccountClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_account(self, account_id: str) -> dict[str, Any]:
        return self._get(f"/v1/accounts/{account_id}")

    def list_account_transactions(self, account_id: str, limit: int = 50) -> dict[str, Any]:
        query = urlencode({"limit": limit})
        return self._get(f"/v1/accounts/{account_id}/transactions?{query}")

    def get_transaction_detail(self, transfer_id: str) -> dict[str, Any]:
        return self._get(f"/v1/transfers/{transfer_id}")

    def check_account_reconciliation(self, account_id: str) -> dict[str, Any]:
        return self._get(f"/v1/accounts/{account_id}/reconciliation")

    def healthz(self) -> dict[str, Any]:
        return self._get("/healthz")

    def _get(self, path: str) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}", headers={"Accept": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            payload = _decode_error_payload(exc)
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            raise GoAPIError(
                status_code=exc.code,
                code=str(error.get("code") or f"HTTP_{exc.code}"),
                message=str(error.get("message") or exc.reason),
                payload=payload,
            ) from exc
        except URLError as exc:
            raise GoAPIError(status_code=None, code="GO_API_UNAVAILABLE", message=str(exc.reason), payload=None) from exc
        except TimeoutError as exc:
            raise GoAPIError(status_code=None, code="GO_API_TIMEOUT", message="Go API request timed out", payload=None) from exc
        except json.JSONDecodeError as exc:
            raise GoAPIError(status_code=None, code="GO_API_BAD_JSON", message="Go API returned invalid JSON", payload=None) from exc


def _decode_error_payload(exc: HTTPError) -> dict[str, Any]:
    try:
        raw = exc.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}
