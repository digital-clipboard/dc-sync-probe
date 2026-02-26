"""Phase 1: Find & Pull Meeting — search, pull DCJSON, apply POA merge."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from rich.console import Console
from rich.prompt import IntPrompt
from rich.table import Table

from .config import Session
from .transport import graphql

console = Console()


# ---------------------------------------------------------------------------
# Step 1a — search
# ---------------------------------------------------------------------------

def search_meetings(session: Session, query: str) -> list[dict[str, Any]]:
    """Search for meetings by client name. Returns deduplicated results."""
    data = graphql(
        session,
        'query($q: String!) { search(query: $q) { data } }',
        variables={"q": query},
        timeout=45.0,
    )
    raw = data.get("search", {}).get("data")
    if not raw:
        return []

    meetings: list[dict] = json.loads(raw) if isinstance(raw, str) else raw

    # Deduplicate by contact1IdSwiftId (mirrors concatMeetings)
    seen: set[str] = set()
    unique: list[dict] = []
    for m in meetings:
        swift = m.get("contact1IdSwiftId", "")
        if swift and swift in seen:
            continue
        if swift:
            seen.add(swift)
        unique.append(m)
    return unique


def pick_meeting(meetings: list[dict[str, Any]]) -> dict[str, Any]:
    """Display search results and let the user pick one."""
    table = Table(title="Search Results")
    table.add_column("#", style="bold")
    table.add_column("Client 1")
    table.add_column("Client 2")
    table.add_column("Address")
    table.add_column("Meeting ID")

    for i, m in enumerate(meetings, 1):
        c2 = m.get("contact2IdFullName") or ""
        addr = (m.get("contact1IdAddress") or "—").replace("\n", ", ")[:50]
        table.add_row(str(i), m.get("contact1IdFullName", "?"), c2, addr, m.get("meetingId", "?"))

    console.print(table)
    idx = IntPrompt.ask("Pick a meeting number", default=1)
    return meetings[idx - 1]


# ---------------------------------------------------------------------------
# Step 1b — pull
# ---------------------------------------------------------------------------

def pull_meeting(
    session: Session,
    swift1: str,
    swift2: str = "",
    meeting_id: str = "",
) -> dict[str, Any]:
    """Download full DCJSON via getMeetingFromCuro."""
    mid_arg = f'meetingId: "{meeting_id}"' if meeting_id else ""
    query = f"""mutation {{
        getMeetingFromCuro(
            swift1: "{swift1}",
            swift2: "{swift2}",
            search: "true",
            {mid_arg}
        ) {{
            success message DCJSON
            client1Id client2Id meetingId
            sfAccountId sfAccountId2
        }}
    }}"""
    data = graphql(session, query, timeout=90.0)
    result = data["getMeetingFromCuro"]
    if not result.get("success"):
        raise RuntimeError(f"getMeetingFromCuro failed: {result.get('message')}")
    dcjson = result["DCJSON"]
    if isinstance(dcjson, str):
        dcjson = json.loads(dcjson)
    return {
        "DCJSON": dcjson,
        "client1Id": result.get("client1Id"),
        "client2Id": result.get("client2Id"),
        "meetingId": result.get("meetingId"),
        "sfAccountId": result.get("sfAccountId"),
        "sfAccountId2": result.get("sfAccountId2"),
    }


# ---------------------------------------------------------------------------
# Step 1c — POA merge  (transformDCJSONForSnapshot)
# ---------------------------------------------------------------------------

def _merge_poa_into_will(
    will_data: dict[str, Any],
    poa_data: dict[str, Any] | None,
    client_key: str,
) -> dict[str, Any]:
    """Merge PowerOfAttorney items into WillArrangements for *client_key*."""
    if not poa_data:
        return will_data
    result = dict(will_data)

    # poaInfo: find matching item by owner
    for item in poa_data.get("poaInfo") or []:
        if item.get("owner") == client_key:
            result.update({
                "powerOfAttoneyType": item.get("powerOfAttoneyType"),
                "powerOfAttoneyInvoked": item.get("powerOfAttoneyInvoked"),
                "powerOfAttoneyInvokedDate": item.get("powerOfAttoneyInvokedDate"),
                "poaInfoId": item.get("id"),
                "poaInfo_SF": item.get("_SF"),
            })
            break

    # poa (attorney): find matching item by owner
    for item in poa_data.get("poa") or []:
        if item.get("owner") == client_key:
            result.update({
                "attorneyFirstName": item.get("attorneyFirstName"),
                "attorneyLastName": item.get("attorneyLastName"),
                "attorneyEmail": item.get("attorneyEmail"),
                "attorneyTelephone": item.get("attorneyTelephone"),
                "attorneyAddress": item.get("attorneyAddress"),
                "swiftId": item.get("swiftId"),
                "alreadySynced": item.get("alreadySynced") or bool(item.get("comesFrom")),
                "poaAttorneyId": item.get("id"),
                "poaAttorney_SF": item.get("_SF"),
            })
            break

    return result


def transform_dcjson(dcjson: dict[str, Any]) -> dict[str, Any]:
    """Apply POA→WillArrangements merge (mirrors transformDCJSONForSnapshot)."""
    result = deepcopy(dcjson)
    poa_data = (result.get("PowerOfAttorney") or {}).get("Client1")

    for client_key in ("Client1", "Client2"):
        will_data = (result.get("WillArrangements") or {}).get(client_key)
        if will_data and poa_data:
            result["WillArrangements"][client_key] = _merge_poa_into_will(
                will_data, poa_data, client_key,
            )
    return result


# ---------------------------------------------------------------------------
# Public: full Phase 1
# ---------------------------------------------------------------------------

def find_and_pull(session: Session, search_term: str) -> dict[str, Any]:
    """Run the complete Phase 1: search → pick → pull → transform.

    Returns dict with keys: DCJSON, meetingId, client1Id, client2Id,
    sfAccountId, sfAccountId2, is_joint.
    """
    console.print(f"\n[bold]Searching for:[/bold] {search_term}")
    meetings = search_meetings(session, search_term)
    if not meetings:
        raise RuntimeError("No meetings found.")
    meeting = pick_meeting(meetings)

    swift1 = meeting["contact1IdSwiftId"]
    swift2 = meeting.get("contact2IdSwiftId") or ""
    is_joint = bool(swift2)
    meeting_id = meeting.get("meetingId", "")

    console.print(f"\n[bold]Pulling meeting[/bold] {meeting_id} ({'joint' if is_joint else 'single'})…")
    result = pull_meeting(session, swift1, swift2, meeting_id)

    console.print("[bold]Applying POA merge transform…[/bold]")
    result["DCJSON"] = transform_dcjson(result["DCJSON"])
    result["is_joint"] = is_joint
    return result
