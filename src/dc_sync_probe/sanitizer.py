"""Phase 2: Sanitize the source DCJSON — PII replacement, ID remapping, metadata stripping."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from .constants import (
    ALL_CARD_TYPES,
    INCOME_EXPENSES_SECTIONS,
    REPEATER_SECTION_MAP,
    SIMPLE_CARDS,
)

# ---------------------------------------------------------------------------
# Step 2a — PII replacement values
# ---------------------------------------------------------------------------

_PII_PERSONAL_DETAILS: dict[str, Any] = {
    "middleName": "TestMiddle",
    "nickname": "TestNickname",
    "dateOfBirth": "1990-01-01",
    "nationalInsuranceNumber": "QQ123456C",
    "maidenName": "TestMaiden",
    "telephone1": "+44 7700 900000",
    "email2": "test.personal@example.com",
    "homeAddress": {
        "line1": "1 Test Street",
        "city": "TestCity",
        "postCode": "TE1 1ST",
    },
}

# Fields we keep from the fresh meeting (not replaced with synthetic values)
_KEEP_FROM_FRESH = {"firstName", "lastName", "email1"}

# Fields excluded from sync entirely (never synced by diffEngine)
_EXCLUDED_FIELDS = {"fullName", "correspondenceAddress"}

_PII_WILL_ARRANGEMENTS: dict[str, Any] = {
    "attorneyFirstName": "TestAttorneyFirst",
    "attorneyLastName": "TestAttorneyLast",
    "attorneyEmail": "test.attorney@example.com",
    "attorneyTelephone": "+44 7700 900001",
    "attorneyAddress": {
        "line1": "2 Test Street",
        "city": "TestCity",
        "postCode": "TE1 2ST",
    },
}

# Metadata fields to strip from repeater items
_STRIP_FIELDS = {
    "comesFrom",
    "_SF",
    "needsSync",
    "hasChanges",
    "swiftId",
    "originalObject",
    "readOnly",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_uuid() -> str:
    return str(uuid.uuid4())


def _is_internal(key: str) -> bool:
    return key.startswith("_")


# ---------------------------------------------------------------------------
# Step 2a — replace PII
# ---------------------------------------------------------------------------

def _sanitize_personal_details(
    dcjson: dict[str, Any],
    fresh: dict[str, Any],
) -> None:
    """Replace PII in PersonalDetails for both clients."""
    for client in ("Client1", "Client2"):
        src = (dcjson.get("PersonalDetails") or {}).get(client)
        if not src:
            continue
        fresh_client = (fresh.get("PersonalDetails") or {}).get(client, {})

        # Keep firstName/lastName/email1 from fresh meeting.
        # If fresh meeting has no data for this client, use synthetic values
        # so we never leak real PII.
        _KEEP_FALLBACKS = {
            "firstName": "TestFirstName",
            "lastName": "TestLastName",
            "email1": "test.work@example.com",
        }
        for field in _KEEP_FROM_FRESH:
            if field in fresh_client:
                src[field] = fresh_client[field]
            elif field in src:
                src[field] = _KEEP_FALLBACKS[field]

        # Clear excluded fields (never synced, but don't leave real PII)
        for field in _EXCLUDED_FIELDS:
            if field in src:
                src[field] = ""

        # Replace remaining PII with synthetic values
        for field, value in _PII_PERSONAL_DETAILS.items():
            if field in src or field in fresh_client:
                src[field] = deepcopy(value)


def _sanitize_family(dcjson: dict[str, Any]) -> None:
    """Replace PII in Family repeater items."""
    for client in ("Client1", "Client2"):
        items = (dcjson.get("Family") or {}).get(client, {}).get("family", [])
        for i, item in enumerate(items, 1):
            item["dependentFirstName"] = f"TestFirst{i}"
            item["dependentLastName"] = f"TestLast{i}"


def _sanitize_will_arrangements(dcjson: dict[str, Any]) -> None:
    """Replace PII in WillArrangements (attorney fields)."""
    for client in ("Client1", "Client2"):
        card = (dcjson.get("WillArrangements") or {}).get(client)
        if not card:
            continue
        for field, value in _PII_WILL_ARRANGEMENTS.items():
            if field in card:
                card[field] = deepcopy(value)


def _sanitize_income_expenses(dcjson: dict[str, Any]) -> None:
    """Replace PII in IncomeExpenses employment items (jobTitle)."""
    for client in ("Client1", "Client2"):
        employment = (dcjson.get("IncomeExpenses") or {}).get(client, {}).get("employment", [])
        for item in employment:
            if "jobTitle" in item:
                item["jobTitle"] = "Test Job Title"


# ---------------------------------------------------------------------------
# Step 2b — remap local IDs
# ---------------------------------------------------------------------------

def _build_id_map(dcjson: dict[str, Any]) -> dict[str, str]:
    """Walk all repeater items and build old→new UUID mapping."""
    id_map: dict[str, str] = {}

    def _collect(items: list[dict]) -> None:
        for item in items:
            old_id = item.get("id")
            if old_id and old_id not in id_map:
                id_map[old_id] = _new_uuid()

    # Standard repeater cards
    for card_name, section_name in REPEATER_SECTION_MAP.items():
        for client in ("Client1", "Client2"):
            items = (dcjson.get(card_name) or {}).get(client, {}).get(section_name, [])
            _collect(items)

    # IncomeExpenses nested sections
    for section in INCOME_EXPENSES_SECTIONS:
        for client in ("Client1", "Client2"):
            items = (dcjson.get("IncomeExpenses") or {}).get(client, {}).get(section, [])
            _collect(items)

    # PowerOfAttorney
    poa = (dcjson.get("PowerOfAttorney") or {}).get("Client1", {})
    _collect(poa.get("poaInfo", []))
    _collect(poa.get("poa", []))

    return id_map


def _apply_id_map(dcjson: dict[str, Any], id_map: dict[str, str]) -> None:
    """Replace every item.id with the mapped new UUID, plus cross-refs."""

    def _remap_items(items: list[dict]) -> None:
        for item in items:
            old_id = item.get("id")
            if old_id and old_id in id_map:
                item["id"] = id_map[old_id]

    # Standard repeater cards
    for card_name, section_name in REPEATER_SECTION_MAP.items():
        for client in ("Client1", "Client2"):
            items = (dcjson.get(card_name) or {}).get(client, {}).get(section_name, [])
            _remap_items(items)

    # IncomeExpenses
    for section in INCOME_EXPENSES_SECTIONS:
        for client in ("Client1", "Client2"):
            items = (dcjson.get("IncomeExpenses") or {}).get(client, {}).get(section, [])
            _remap_items(items)

    # PowerOfAttorney
    poa = (dcjson.get("PowerOfAttorney") or {}).get("Client1", {})
    _remap_items(poa.get("poaInfo", []))
    _remap_items(poa.get("poa", []))

    # Cross-references in WillArrangements (poaInfoId, poaAttorneyId)
    for client in ("Client1", "Client2"):
        will = (dcjson.get("WillArrangements") or {}).get(client)
        if not will:
            continue
        for ref_field in ("poaInfoId", "poaAttorneyId"):
            old_ref = will.get(ref_field)
            if old_ref and old_ref in id_map:
                will[ref_field] = id_map[old_ref]


# ---------------------------------------------------------------------------
# Step 2c — strip sync metadata
# ---------------------------------------------------------------------------

def _strip_repeater_metadata(dcjson: dict[str, Any]) -> None:
    """Remove comesFrom, _SF, needsSync, etc. from all repeater items."""

    def _strip_items(items: list[dict]) -> None:
        for item in items:
            for field in list(item.keys()):
                if field in _STRIP_FIELDS or _is_internal(field):
                    del item[field]

    for card_name, section_name in REPEATER_SECTION_MAP.items():
        for client in ("Client1", "Client2"):
            items = (dcjson.get(card_name) or {}).get(client, {}).get(section_name, [])
            _strip_items(items)

    for section in INCOME_EXPENSES_SECTIONS:
        for client in ("Client1", "Client2"):
            items = (dcjson.get("IncomeExpenses") or {}).get(client, {}).get(section, [])
            _strip_items(items)

    poa = (dcjson.get("PowerOfAttorney") or {}).get("Client1", {})
    _strip_items(poa.get("poaInfo", []))
    _strip_items(poa.get("poa", []))


def _replace_simple_card_sf(
    dcjson: dict[str, Any],
    fresh: dict[str, Any],
) -> None:
    """For simple cards, replace _SF with the fresh meeting's _SF."""
    for card_name in SIMPLE_CARDS:
        for client in ("Client1", "Client2"):
            sanitized_card = (dcjson.get(card_name) or {}).get(client)
            fresh_card = (fresh.get(card_name) or {}).get(client)
            if sanitized_card and fresh_card:
                sanitized_card["_SF"] = deepcopy(fresh_card.get("_SF", {}))


# WillArrangements POA sync-state fields that reference the SOURCE meeting's
# SF records. Reset them so the diff engine treats attorneys as new (CREATE).
_WILL_POA_SYNC_STATE_RESETS: dict[str, Any] = {
    "alreadySynced": False,
    "swiftId": "",
    "poaAttorney_SF": {},
}


def _reset_will_arrangements_poa_state(dcjson: dict[str, Any]) -> None:
    """Clear attorney sync-state fields from WillArrangements simple card."""
    for client in ("Client1", "Client2"):
        card = (dcjson.get("WillArrangements") or {}).get(client)
        if not card:
            continue
        for field, reset_value in _WILL_POA_SYNC_STATE_RESETS.items():
            if field in card:
                card[field] = reset_value


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def sanitize(
    source_dcjson: dict[str, Any],
    fresh_dcjson: dict[str, Any],
    return_id_map: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, str]]:
    """Full Phase 2: sanitize *source_dcjson* using *fresh_dcjson* as reference.

    Returns a new sanitized DCJSON ready for the diff engine.
    If *return_id_map* is True, returns (sanitized_dcjson, id_map) where
    id_map is {old_uuid: new_uuid} for all remapped repeater items.
    """
    dcjson = deepcopy(source_dcjson)

    # 2a — PII
    _sanitize_personal_details(dcjson, fresh_dcjson)
    _sanitize_family(dcjson)
    _sanitize_will_arrangements(dcjson)
    _sanitize_income_expenses(dcjson)

    # 2b — remap local IDs
    id_map = _build_id_map(dcjson)
    _apply_id_map(dcjson, id_map)

    # 2c — strip sync metadata + replace simple card _SF
    _strip_repeater_metadata(dcjson)
    _replace_simple_card_sf(dcjson, fresh_dcjson)
    _reset_will_arrangements_poa_state(dcjson)

    if return_id_map:
        return dcjson, id_map
    return dcjson
