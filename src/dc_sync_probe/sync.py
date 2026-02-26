"""Phase 4: Sync changes — send CREATE then UPDATE via GraphQL mutations."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console

from .config import Session
from .transport import TransportError, graphql

console = Console()

_SOURCE = "ios"

_SYNC_CREATE_MUTATION = """
mutation SyncCreateChanges(
  $meetingId: UUID!,
  $changes: [ChangeProperInput!]!,
  $initialDCJSON: JSON!,
  $currentDCJSON: JSON!,
  $source: String!
) {
  syncCreateChanges(
    meetingId: $meetingId,
    changes: $changes,
    initialDCJSON: $initialDCJSON,
    currentDCJSON: $currentDCJSON,
    source: $source
  ) {
    success
    message
    results
  }
}
"""

_SYNC_UPDATE_MUTATION = """
mutation SyncUpdateChanges(
  $meetingId: UUID!,
  $changes: [ChangeProperInput!]!,
  $initialDCJSON: JSON!,
  $currentDCJSON: JSON!,
  $source: String!
) {
  syncUpdateChanges(
    meetingId: $meetingId,
    changes: $changes,
    initialDCJSON: $initialDCJSON,
    currentDCJSON: $currentDCJSON,
    source: $source
  ) {
    success
    message
  }
}
"""


def _send_changes(
    session: Session,
    mutation: str,
    mutation_name: str,
    meeting_id: str,
    changes: list[dict[str, Any]],
    initial_dcjson: dict[str, Any],
    current_dcjson: dict[str, Any],
) -> dict[str, Any]:
    if not changes:
        return {"success": True, "message": "No changes", "results": {}}

    variables = {
        "meetingId": meeting_id,
        "changes": changes,
        "initialDCJSON": initial_dcjson,
        "currentDCJSON": current_dcjson,
        "source": _SOURCE,
    }

    try:
        data = graphql(session, mutation, variables=variables, timeout=60.0)
    except TransportError:
        raise
    except Exception as exc:
        # Network / timeout errors — re-raise with context
        raise TransportError(f"{mutation_name} transport error: {exc}") from exc

    result = data.get(mutation_name, {})
    if not result:
        return {"success": False, "message": f"No response from {mutation_name}", "results": {}}

    # Parse stringified results
    results = result.get("results", {})
    if isinstance(results, str):
        try:
            results = json.loads(results)
        except (json.JSONDecodeError, TypeError):
            results = {}

    return {
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "results": results or {},
    }


def sync_create_changes(
    session: Session,
    meeting_id: str,
    changes: list[dict[str, Any]],
    initial_dcjson: dict[str, Any],
    current_dcjson: dict[str, Any],
) -> dict[str, Any]:
    """Send CREATE changes. Returns {success, message, results}."""
    console.print(f"  Syncing [bold]{len(changes)}[/bold] CREATE changes…")
    return _send_changes(
        session,
        _SYNC_CREATE_MUTATION,
        "syncCreateChanges",
        meeting_id,
        changes,
        initial_dcjson,
        current_dcjson,
    )


def sync_update_changes(
    session: Session,
    meeting_id: str,
    changes: list[dict[str, Any]],
    initial_dcjson: dict[str, Any],
    current_dcjson: dict[str, Any],
) -> dict[str, Any]:
    """Send UPDATE changes. Must run after CREATE completes."""
    console.print(f"  Syncing [bold]{len(changes)}[/bold] UPDATE changes…")
    return _send_changes(
        session,
        _SYNC_UPDATE_MUTATION,
        "syncUpdateChanges",
        meeting_id,
        changes,
        initial_dcjson,
        current_dcjson,
    )
