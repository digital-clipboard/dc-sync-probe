"""Change generator — creates properly formatted change objects for the sync system.

Mirrors changeGenerator.js from dcReact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .sobject_resolver import get_sobject_names, is_joint_item


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_simple_change(
    *,
    card_name: str,
    client_number: str,
    field_name: str,
    val: Any,
    old_val: Any,
    meeting_id: str,
    form_data: dict[str, Any],
) -> dict[str, Any]:
    """Create a change object for a simple card field update."""
    path = [card_name, client_number, field_name]
    return {
        "op": "update",
        "path": path,
        "slag": ".".join(path),
        "dcId": form_data.get("id"),
        "type": "simple",
        "val": val,
        "oldVal": old_val,
        "syncable": True,
        "formData": form_data,
        "meetingId": meeting_id,
        "fieldName": field_name,
        "parentName": field_name,
        "joint": False,
        "joinedJoint": False,
        "timestamp": _now_iso(),
    }


def create_repeater_create_changes(
    *,
    card_name: str,
    client_number: str,
    section_name: str,
    item: dict[str, Any],
    meeting_id: str,
) -> list[dict[str, Any]]:
    """Create change object(s) for a new repeater item.

    Family / POA return 2+ changes (ContactAccount + ContactRelation).
    """
    sobject_names = get_sobject_names(card_name, section_name, item)
    joint = is_joint_item(item)
    item_id = item.get("id", "")

    is_contact_relation_card = (
        card_name in ("Family", "PowerOfAttorney") and len(sobject_names) == 2
    )

    if is_contact_relation_card:
        changes: list[dict[str, Any]] = []
        contact_account_so = sobject_names[0]
        contact_relation_so = sobject_names[1]

        owner_for_form = (
            ["Client1", "Client2"] if joint
            else (item["owner"][0] if isinstance(item.get("owner"), list) else item.get("owner"))
        )
        item_normalized = {**item, "owner": owner_for_form}

        # ContactAccount — always path Client1
        ca_path = [card_name, "Client1", section_name, item_id, contact_account_so]
        changes.append({
            "op": "create",
            "path": ca_path,
            "slag": ".".join(ca_path),
            "dcId": item_id,
            "type": "repeater",
            "val": item_normalized,
            "formData": item_normalized,
            "syncable": True,
            "meetingId": meeting_id,
            "fieldName": contact_account_so,
            "parentName": contact_account_so,
            "sObjectName": contact_account_so,
            "joint": joint,
            "joinedJoint": False,
            "timestamp": _now_iso(),
        })

        # ContactRelation — path depends on owner / joint
        relation_clients = ["Client1", "Client2"] if joint else [
            item["owner"][0] if isinstance(item.get("owner"), list) else item.get("owner", client_number)
        ]
        for rc in relation_clients:
            cr_path = [card_name, rc, section_name, item_id, contact_relation_so]
            changes.append({
                "op": "create",
                "path": cr_path,
                "slag": ".".join(cr_path),
                "dcId": item_id,
                "type": "repeater",
                "val": item_normalized,
                "formData": item_normalized,
                "syncable": True,
                "meetingId": meeting_id,
                "fieldName": contact_relation_so,
                "parentName": contact_relation_so,
                "sObjectName": contact_relation_so,
                "joint": joint,
                "joinedJoint": False,
                "timestamp": _now_iso(),
            })
        return changes

    # Joint financial: Account on Client1, Role on Client2
    is_joint_financial = joint and len(sobject_names) == 2

    result: list[dict[str, Any]] = []
    for idx, so_name in enumerate(sobject_names):
        owner = item["owner"][0] if isinstance(item.get("owner"), list) else item.get("owner")
        if is_joint_financial:
            path_client = "Client1" if idx == 0 else "Client2"
        elif joint:
            path_client = "Joint"
        else:
            path_client = owner or client_number

        path = [card_name, path_client, section_name, item_id, so_name]
        result.append({
            "op": "create",
            "path": path,
            "slag": ".".join(path),
            "dcId": item_id,
            "type": "repeater",
            "val": item,
            "formData": item,
            "syncable": True,
            "meetingId": meeting_id,
            "fieldName": so_name,
            "parentName": so_name,
            "sObjectName": so_name,
            "joint": joint,
            "joinedJoint": False,
            "timestamp": _now_iso(),
        })
    return result


def create_repeater_update_change(
    *,
    card_name: str,
    client_number: str,
    section_name: str,
    item: dict[str, Any],
    field_name: str,
    val: Any,
    old_val: Any,
    meeting_id: str,
) -> dict[str, Any]:
    """Create a change object for a repeater item field update."""
    sobject_names = get_sobject_names(card_name, section_name, item)
    so_name = sobject_names[0] if sobject_names else None
    joint = is_joint_item(item)
    owner = item["owner"][0] if isinstance(item.get("owner"), list) else item.get("owner")
    path_client = "Joint" if joint else (owner or client_number)

    path = [card_name, path_client, section_name, item.get("id", ""), field_name]
    return {
        "op": "update",
        "path": path,
        "slag": ".".join(path),
        "dcId": item.get("id"),
        "type": "repeater",
        "val": val,
        "oldVal": old_val,
        "formData": item,
        "syncable": True,
        "meetingId": meeting_id,
        "fieldName": field_name,
        "parentName": field_name,
        "sObjectName": so_name,
        "joint": joint,
        "joinedJoint": False,
        "timestamp": _now_iso(),
    }
