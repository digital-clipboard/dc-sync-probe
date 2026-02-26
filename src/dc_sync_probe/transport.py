"""HTTP / GraphQL transport layer (replaces dcReact's transporter.js)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .config import DEFAULT_TIMEOUT, Session

# Session-expired markers from transporter.js logOutIfNeeded
_SESSION_EXPIRED_MARKERS = (
    "invalid signature",
    "you must be authenticated",
    "token_session_timeout",
    "jwtautherror",
    "status code 401",
)


class TransportError(Exception):
    """Raised on non-retryable transport failures."""


class SessionExpiredError(TransportError):
    """Raised when the backend says the JWT is no longer valid."""


class GraphQLError(TransportError):
    """Raised when the GraphQL response contains an errors array."""

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        msg = errors[0].get("message", str(errors)) if errors else "Unknown GraphQL error"
        super().__init__(msg)


def _check_session_expired(status_code: int, body: dict | None) -> None:
    if status_code == 401:
        raise SessionExpiredError("HTTP 401 — session expired")
    if body is None:
        return
    # Walk through possible message locations (mirrors logOutIfNeeded)
    for path in (
        ("err", "message"),
        ("message",),
        ("error", "name"),
    ):
        node = body
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
                break
        if isinstance(node, str):
            lower = node.lower()
            if any(marker in lower for marker in _SESSION_EXPIRED_MARKERS):
                raise SessionExpiredError(f"Session expired: {node}")


def graphql(
    session: Session,
    query: str,
    variables: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Execute a GraphQL request and return the ``data`` dict.

    Raises on transport errors, session expiration, or GraphQL-level errors.
    """
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            session.graphql_url,
            headers=session.headers,
            content=json.dumps(payload),
        )

    _check_session_expired(resp.status_code, resp.json() if resp.content else None)
    resp.raise_for_status()

    body = resp.json()
    if "errors" in body and body["errors"]:
        raise GraphQLError(body["errors"])

    return body.get("data", {})


def post_json(
    session: Session,
    url: str,
    body: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Plain POST returning the JSON body (used for /signin)."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=session.headers, json=body)

    _check_session_expired(resp.status_code, resp.json() if resp.content else None)
    resp.raise_for_status()
    return resp.json()
