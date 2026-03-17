"""Remap IDs in production change objects for staging replay.

Two strategies:
1. ID map (deterministic): use the source→cloned ID map from a prior clone
2. Fingerprint (fallback): match items by non-ID field values in the pulled meeting
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .constants import (
    INCOME_EXPENSES_SECTIONS,
    REPEATER_SECTION_MAP,
    SKIP_REPEATER_FIELDS,
)


# ---------------------------------------------------------------------------
# Strategy 1: ID-map based remapping (deterministic, used after clone)
# ---------------------------------------------------------------------------

def remap_change_with_id_map(
    change: dict[str, Any],
    id_map: dict[str, str],
    meeting_id: str,
) -> dict[str, Any]:
    """Remap a single change using a source→cloned ID map."""
    c = deepcopy(change)
    c["meetingId"] = meeting_id

    dc_id = c.get("dcId", "")
    new_id = id_map.get(dc_id)

    if new_id:
        old_id = dc_id
        c["dcId"] = new_id
        if c.get("formData"):
            c["formData"]["id"] = new_id
        c["path"] = [new_id if seg == old_id else seg for seg in c.get("path", [])]
        slag = c.get("slag", "")
        if old_id in slag:
            c["slag"] = slag.replace(old_id, new_id)

    return c


def remap_changes_with_id_map(
    changes: list[dict[str, Any]],
    id_map: dict[str, str],
    meeting_id: str,
) -> list[dict[str, Any]]:
    """Remap all changes using an ID map."""
    return [remap_change_with_id_map(c, id_map, meeting_id) for c in changes]


# ---------------------------------------------------------------------------
# Strategy 2: Fingerprint-based remapping (fallback, no prior clone)
# ---------------------------------------------------------------------------

_FINGERPRINT_IGNORE = SKIP_REPEATER_FIELDS | {"id", "_SF", "comesFrom"}
_PII_FIELDS = {
    "dependentFirstName", "dependentLastName",
    "attorneyFirstName", "attorneyLastName", "attorneyEmail",
    "attorneyTelephone", "attorneyAddress",
    "jobTitle",
}


def _item_fingerprint(item: dict[str, Any]) -> str:
    """Create a fingerprint from syncable, non-ID fields."""
    parts: list[str] = []
    for k in sorted(item):
        if k in _FINGERPRINT_IGNORE or k in _PII_FIELDS or k.startswith("_"):
            continue
        parts.append(f"{k}={item[k]!r}")
    return "|".join(parts)


def build_fingerprint_id_map(
    source_dcjson: dict[str, Any],
    target_dcjson: dict[str, Any],
) -> dict[str, str]:
    """Build source_id→target_id map by matching items via data fingerprint.

    Walks all repeater sections in both DCJSONs, fingerprints each item,
    and maps source item IDs to target item IDs where fingerprints match.
    """
    id_map: dict[str, str] = {}

    def _match_items(source_items: list[dict], target_items: list[dict]) -> None:
        target_fps: dict[str, str] = {}
        for item in target_items:
            fp = _item_fingerprint(item)
            item_id = item.get("id", "")
            if fp and item_id:
                target_fps[fp] = item_id

        for item in source_items:
            fp = _item_fingerprint(item)
            source_id = item.get("id", "")
            if fp and source_id and fp in target_fps:
                id_map[source_id] = target_fps[fp]

    # Standard repeater cards
    for card_name, section_name in REPEATER_SECTION_MAP.items():
        for client in ("Client1", "Client2"):
            src_items = (source_dcjson.get(card_name) or {}).get(client, {}).get(section_name, [])
            tgt_items = (target_dcjson.get(card_name) or {}).get(client, {}).get(section_name, [])
            _match_items(src_items, tgt_items)

    # IncomeExpenses
    for section in INCOME_EXPENSES_SECTIONS:
        for client in ("Client1", "Client2"):
            src_items = (source_dcjson.get("IncomeExpenses") or {}).get(client, {}).get(section, [])
            tgt_items = (target_dcjson.get("IncomeExpenses") or {}).get(client, {}).get(section, [])
            _match_items(src_items, tgt_items)

    return id_map
