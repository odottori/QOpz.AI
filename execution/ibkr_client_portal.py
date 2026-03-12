"""IBKR Client Portal Gateway (CP Web API) minimal client.

Scope: F3-T1 (Paper Trading Setup) — connectivity + read-only account/position queries.

Design goals:
- Zero third-party dependencies (urllib only).
- PowerShell-friendly CLI integration.
- Safe-by-default: does NOT attempt to automate authentication.

Notes:
- For retail accounts, IBKR requires authentication via browser on the same machine
  where the Client Portal Gateway is running.
- The local gateway typically exposes HTTPS on localhost (self-signed cert).
  Use `insecure=True` for localhost workflows.

Endpoints referenced from IBKR CP Web API v1.0 docs:
- GET  /sso/validate
- POST /tickle
- GET  /portfolio/accounts
- GET  /portfolio/{accountId}/summary
- GET  /portfolio/{accountId}/positions/{pageId}
- GET  /iserver/accounts
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    status: int
    url: str
    data: Optional[Any] = None
    error: Optional[str] = None


class IBKRClientPortalError(RuntimeError):
    pass


class IBKRClientPortalClient:
    def __init__(
        self,
        base_url: str = "https://localhost:5000/v1/api",
        *,
        insecure: bool = True,
        timeout_s: float = 5.0,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.insecure = insecure
        self.timeout_s = float(timeout_s)
        self.extra_headers = dict(extra_headers or {})

        self._ssl_ctx = None
        if self.insecure:
            # Local CP Gateway uses self-signed cert; allow opt-out in the CLI.
            self._ssl_ctx = ssl._create_unverified_context()  # noqa: SLF001

    def _build_url(self, path: str, *, query: Optional[Dict[str, str]] = None) -> str:
        path_clean = ("/" + path.lstrip("/")).rstrip("/")
        url = self.base_url + path_clean
        if query:
            url += "?" + urllib.parse.urlencode(query)
        return url

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
    ) -> HttpResult:
        url = self._build_url(path, query=query)
        headers = {
            "Accept": "application/json",
            **self.extra_headers,
        }

        data_bytes = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url=url, method=method.upper(), data=data_bytes, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s, context=self._ssl_ctx) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read()
                if not raw:
                    return HttpResult(ok=200 <= status < 300, status=status, url=url, data=None)
                try:
                    parsed = json.loads(raw.decode("utf-8", errors="replace"))
                except Exception:
                    parsed = raw.decode("utf-8", errors="replace")
                return HttpResult(ok=200 <= status < 300, status=status, url=url, data=parsed)
        except urllib.error.HTTPError as e:
            raw = None
            try:
                raw = e.read()
            except Exception:
                raw = None
            msg = f"HTTPError {getattr(e, 'code', '?')} {getattr(e, 'reason', '')}".strip()
            if raw:
                try:
                    payload = raw.decode("utf-8", errors="replace")
                    msg = msg + f" | body={payload[:500]}"
                except Exception:
                    pass
            return HttpResult(ok=False, status=int(getattr(e, "code", 0) or 0), url=url, error=msg)
        except urllib.error.URLError as e:
            return HttpResult(ok=False, status=0, url=url, error=f"URLError {e!r}")
        except Exception as e:
            return HttpResult(ok=False, status=0, url=url, error=f"Error {e!r}")

    # ---- Convenience API ----

    def sso_validate(self) -> HttpResult:
        return self._request("GET", "/sso/validate")

    def tickle(self) -> HttpResult:
        return self._request("POST", "/tickle", body={})

    def portfolio_accounts(self) -> HttpResult:
        return self._request("GET", "/portfolio/accounts")

    def portfolio_summary(self, account_id: str) -> HttpResult:
        return self._request("GET", f"/portfolio/{account_id}/summary")

    def portfolio_positions(self, account_id: str, page_id: int = 0) -> HttpResult:
        return self._request("GET", f"/portfolio/{account_id}/positions/{int(page_id)}")

    def iserver_accounts(self) -> HttpResult:
        return self._request("GET", "/iserver/accounts")


def pick_first_account_id(payload: Any) -> Optional[str]:
    """Extract a plausible accountId from /portfolio/accounts payload."""
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            for k in ("accountId", "id", "account", "acctId"):
                v = first.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        if isinstance(first, str) and first.strip():
            return first.strip()

    if isinstance(payload, dict):
        # Some endpoints return {"accounts": [...]}.
        for k in ("accounts", "data"):
            v = payload.get(k)
            if isinstance(v, list) and v:
                return pick_first_account_id(v)

    return None


def parse_bool(obj: Any, key: str) -> Optional[bool]:
    if isinstance(obj, dict) and key in obj:
        v = obj.get(key)
        if isinstance(v, bool):
            return v
    return None


def extract_auth_status_from_tickle(tickle_payload: Any) -> Tuple[Optional[bool], Optional[bool]]:
    """Return (authenticated, connected) from tickle response, if present."""
    if not isinstance(tickle_payload, dict):
        return None, None

    iserver = tickle_payload.get("iserver")
    if not isinstance(iserver, dict):
        return None, None

    auth_status = iserver.get("authStatus")
    if not isinstance(auth_status, dict):
        return None, None

    return parse_bool(auth_status, "authenticated"), parse_bool(auth_status, "connected")
