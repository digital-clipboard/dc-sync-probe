"""Phase 3: Diff engine — generates all CREATE + UPDATE changes between two DCJSONs.

Faithful port of dcReact's diffEngine.js.
"""

from __future__ import annotations

import uuid
from typing import Any

from .change_generator import (
    create_repeater_create_changes,
    create_repeater_update_change,
    create_simple_change,
)
from .constants import (
    ALL_POA_FIELDS,
    EXCLUDE_FROM_FORM_DATA,
    INCOME_EXPENSES_SECTIONS,
    POA_ATTORNEY_FIELDS,
    POA_INFO_FIELDS,
    REPEATER_CARDS,
    REPEATER_SECTION_MAP,
    SIMPLE_CARDS,
    SKIP_REPEATER_FIELDS,
    SKIP_SIMPLE_CARD_FIELDS,
)
from .mandatory import has_mandatory_fields_filled
from .sobject_resolver import is_joint_item, needs_create

# ---------------------------------------------------------------------------
# Value comparison helpers
# ---------------------------------------------------------------------------


def _is_empty(val: Any) -> bool:
    if val is None or val == "" or val is False or val == 0:
        return True
    if isinstance(val, (list, dict)) and len(val) == 0:
        return True
    return False


def _is_noise(original: Any, current: Any) -> bool:
    """A noise change: original undefined + current empty, or both empty."""
    if original is None and _is_empty(current):
        return True
    if _is_empty(original) and _is_empty(current):
        return True
    return False


def _deep_equal(a: Any, b: Any) -> bool:
    if a is b:
        return True
    if a is None or b is None:
        return a is b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a) != set(b):
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_deep_equal(x, y) for x, y in zip(a, b))
    return a == b


def _should_skip_simple(field: str) -> bool:
    return field.startswith("_") or field in SKIP_SIMPLE_CARD_FIELDS


def _should_skip_repeater(field: str) -> bool:
    return field.startswith("_") or field in SKIP_REPEATER_FIELDS


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def _get_repeater_items(
    state: dict, card_name: str, client: str, section: str,
) -> list[dict]:
    card = (state.get(card_name) or {}).get(client)
    if not card:
        return []
    items = card.get(section, [])
    return items if isinstance(items, list) else []


def _diff_repeater_item_fields(
    orig_item: dict,
    cur_item: dict,
    card_name: str,
    client: str,
    section: str,
    meeting_id: str,
) -> list[dict]:
    changes: list[dict] = []
    for field in cur_item:
        if _should_skip_repeater(field):
            continue
        orig_val = orig_item.get(field)
        cur_val = cur_item[field]
        if _is_noise(orig_val, cur_val):
            continue
        if not _deep_equal(orig_val, cur_val):
            changes.append(create_repeater_update_change(
                card_name=card_name,
                client_number=client,
                section_name=section,
                item=cur_item,
                field_name=field,
                val=cur_val,
                old_val=orig_val,
                meeting_id=meeting_id,
            ))
    return changes


# ---------------------------------------------------------------------------
# Diff simple card
# ---------------------------------------------------------------------------

def diff_simple_card(
    original: dict, current: dict, card_name: str, meeting_id: str,
) -> list[dict]:
    changes: list[dict] = []
    for client in ("Client1", "Client2"):
        orig_card = (original.get(card_name) or {}).get(client)
        cur_card = (current.get(card_name) or {}).get(client)
        if not cur_card:
            continue

        # Build formData
        form_data = {
            k: v for k, v in cur_card.items() if k not in EXCLUDE_FROM_FORM_DATA
        }
        if orig_card:
            form_data["_SF"] = orig_card.get("_SF")

        for field in cur_card:
            if _should_skip_simple(field):
                continue
            orig_val = orig_card.get(field) if orig_card else None
            cur_val = cur_card[field]
            if _is_noise(orig_val, cur_val):
                continue
            if not _deep_equal(orig_val, cur_val):
                changes.append(create_simple_change(
                    card_name=card_name,
                    client_number=client,
                    field_name=field,
                    val=cur_val,
                    old_val=orig_val,
                    meeting_id=meeting_id,
                    form_data=form_data,
                ))
    return changes


# ---------------------------------------------------------------------------
# Diff repeater card
# ---------------------------------------------------------------------------

def diff_repeater_card(
    original: dict, current: dict, card_name: str, meeting_id: str,
) -> tuple[list[dict], list[dict]]:
    creates: list[dict] = []
    updates: list[dict] = []
    section = REPEATER_SECTION_MAP.get(card_name, card_name.lower())
    is_two_client = bool((current.get("PersonalDetails") or {}).get("Client2", {}).get("firstName"))

    for client in ("Client1", "Client2"):
        orig_items = _get_repeater_items(original, card_name, client, section)
        cur_items = _get_repeater_items(current, card_name, client, section)

        orig_by_id = {it["id"]: it for it in orig_items if it.get("id")}

        for cur in cur_items:
            if not cur.get("id"):
                continue
            orig = orig_by_id.get(cur["id"])

            if not orig or needs_create(cur):
                if not has_mandatory_fields_filled(cur, card_name, is_two_client):
                    continue
                creates.extend(create_repeater_create_changes(
                    card_name=card_name,
                    client_number=client,
                    section_name=section,
                    item=cur,
                    meeting_id=meeting_id,
                ))
            else:
                item_with_sf = {**cur, "_SF": orig.get("_SF")}
                updates.extend(_diff_repeater_item_fields(
                    orig, item_with_sf, card_name, client, section, meeting_id,
                ))
    return creates, updates


# ---------------------------------------------------------------------------
# Split joint income/expenditure items
# ---------------------------------------------------------------------------

def _split_joint_item(item: dict, client: str) -> dict:
    amount_gbp = item["amount"]["amount"]["amountGBP"]
    half = round(amount_gbp / 2, 2)
    half_converted = f"£{half:,.2f}"
    half_masked = f"£{half:,.2f}"

    return {
        **item,
        "id": str(uuid.uuid4()) if client == "Client2" else item["id"],
        "owner": client,
        "amount": {
            **item["amount"],
            "amount": {
                **item["amount"]["amount"],
                "amountGBP": half,
                "amountConverted": half_converted,
                "amountMasked": half_masked,
            },
        },
    }


# ---------------------------------------------------------------------------
# Diff IncomeExpenses
# ---------------------------------------------------------------------------

def diff_income_expenses(
    original: dict, current: dict, meeting_id: str,
) -> tuple[list[dict], list[dict]]:
    creates: list[dict] = []
    updates: list[dict] = []
    card = "IncomeExpenses"
    is_two_client = bool((current.get("PersonalDetails") or {}).get("Client2", {}).get("firstName"))

    for section in INCOME_EXPENSES_SECTIONS:
        for client in ("Client1", "Client2"):
            orig_items = _get_repeater_items(original, card, client, section)
            cur_items = _get_repeater_items(current, card, client, section)
            orig_by_id = {it["id"]: it for it in orig_items if it.get("id")}

            for cur in cur_items:
                if not cur.get("id"):
                    continue
                orig = orig_by_id.get(cur["id"])

                if not orig or needs_create(cur):
                    if not has_mandatory_fields_filled(cur, card, is_two_client):
                        continue

                    # Joint split for income / expenditure
                    if is_joint_item(cur) and section in ("income", "expenditure"):
                        for split_client in ("Client1", "Client2"):
                            split = _split_joint_item(cur, split_client)
                            creates.extend(create_repeater_create_changes(
                                card_name=card,
                                client_number=split_client,
                                section_name=section,
                                item=split,
                                meeting_id=meeting_id,
                            ))
                    else:
                        creates.extend(create_repeater_create_changes(
                            card_name=card,
                            client_number=client,
                            section_name=section,
                            item=cur,
                            meeting_id=meeting_id,
                        ))
                else:
                    item_with_sf = {**cur, "_SF": orig.get("_SF")}
                    updates.extend(_diff_repeater_item_fields(
                        orig, item_with_sf, card, client, section, meeting_id,
                    ))
    return creates, updates


# ---------------------------------------------------------------------------
# Diff Notes / ClientNeeds
# ---------------------------------------------------------------------------

def _diff_keyed_card(
    original: dict, current: dict, card_name: str, meeting_id: str,
) -> list[dict]:
    changes: list[dict] = []
    for client in ("Client1", "Client2"):
        orig = (original.get(card_name) or {}).get(client)
        cur = (current.get(card_name) or {}).get(client)
        if not cur:
            continue
        form_data = {
            **cur,
            "id": orig.get("id") if orig else None,
            "_SF": orig.get("_SF") if orig else None,
        }
        for field in cur:
            if field.startswith("_") or field == "id":
                continue
            orig_val = orig.get(field) if orig else None
            cur_val = cur[field]
            if _is_noise(orig_val, cur_val):
                continue
            if not _deep_equal(orig_val, cur_val):
                changes.append(create_simple_change(
                    card_name=card_name,
                    client_number=client,
                    field_name=field,
                    val=cur_val,
                    old_val=orig_val,
                    meeting_id=meeting_id,
                    form_data=form_data,
                ))
    return changes


# ---------------------------------------------------------------------------
# Diff WillArrangements (special POA handling)
# ---------------------------------------------------------------------------

def diff_will_arrangements(
    original: dict, current: dict, meeting_id: str,
) -> tuple[list[dict], list[dict]]:
    creates: list[dict] = []
    updates: list[dict] = []

    for client in ("Client1", "Client2"):
        orig_card = (original.get("WillArrangements") or {}).get(client)
        cur_card = (current.get("WillArrangements") or {}).get(client)
        if not cur_card:
            continue

        will_form = {**cur_card, "_SF": orig_card.get("_SF") if orig_card else None}

        # Regular WillArrangements fields (exclude all POA fields)
        for field in cur_card:
            if _should_skip_simple(field) or field in ALL_POA_FIELDS:
                continue
            orig_val = orig_card.get(field) if orig_card else None
            cur_val = cur_card[field]
            if _is_noise(orig_val, cur_val):
                continue
            if not _deep_equal(orig_val, cur_val):
                updates.append(create_simple_change(
                    card_name="WillArrangements",
                    client_number=client,
                    field_name=field,
                    val=cur_val,
                    old_val=orig_val,
                    meeting_id=meeting_id,
                    form_data=will_form,
                ))

        # POA info → repeater UPDATE changes
        poa_info_item = {
            "id": cur_card.get("poaInfoId") or str(uuid.uuid4()),
            "_SF": cur_card.get("poaInfo_SF") or (orig_card.get("poaInfo_SF") if orig_card else None),
            "powerOfAttoneyType": cur_card.get("powerOfAttoneyType", ""),
            "powerOfAttoneyInvoked": cur_card.get("powerOfAttoneyInvoked", ""),
            "powerOfAttoneyInvokedDate": cur_card.get("powerOfAttoneyInvokedDate", ""),
            "owner": cur_card.get("owner", client),
            "comesFrom": cur_card.get("comesFrom", "Account"),
        }

        for field in POA_INFO_FIELDS:
            orig_val = orig_card.get(field) if orig_card else None
            cur_val = cur_card.get(field)
            if _is_noise(orig_val, cur_val):
                continue
            if not _deep_equal(orig_val, cur_val):
                updates.append(create_repeater_update_change(
                    card_name="PowerOfAttorney",
                    client_number=client,
                    section_name="poaInfo",
                    item=poa_info_item,
                    field_name=field,
                    val=cur_val,
                    old_val=orig_val,
                    meeting_id=meeting_id,
                ))

        # Attorney — CREATE (new) or UPDATE (existing)
        has_attorney = cur_card.get("attorneyFirstName") or cur_card.get("attorneyLastName")
        already_synced = cur_card.get("alreadySynced")

        if has_attorney and not already_synced:
            create_item = {
                "id": cur_card.get("poaAttorneyId") or str(uuid.uuid4()),
                "owner": client,
                "attorneyFirstName": cur_card.get("attorneyFirstName", ""),
                "attorneyLastName": cur_card.get("attorneyLastName", ""),
                "attorneyEmail": cur_card.get("attorneyEmail", ""),
                "attorneyTelephone": cur_card.get("attorneyTelephone", ""),
                "attorneyAddress": cur_card.get("attorneyAddress"),
                "swiftId": cur_card.get("swiftId", ""),
                "unconfirmed": False,
            }
            creates.extend(create_repeater_create_changes(
                card_name="PowerOfAttorney",
                client_number=client,
                section_name="poa",
                item=create_item,
                meeting_id=meeting_id,
            ))
        elif already_synced:
            attorney_item = {
                "id": cur_card.get("poaAttorneyId") or str(uuid.uuid4()),
                "_SF": cur_card.get("poaAttorney_SF") or (orig_card.get("poaAttorney_SF") if orig_card else None),
                "attorneyFirstName": cur_card.get("attorneyFirstName", ""),
                "attorneyLastName": cur_card.get("attorneyLastName", ""),
                "attorneyEmail": cur_card.get("attorneyEmail", ""),
                "attorneyTelephone": cur_card.get("attorneyTelephone", ""),
                "attorneyAddress": cur_card.get("attorneyAddress"),
                "swiftId": cur_card.get("swiftId", ""),
                "owner": client,
                "comesFrom": cur_card.get("comesFrom", "ContactAccount"),
            }
            for field in POA_ATTORNEY_FIELDS:
                if field in ("swiftId", "deleteRelation", "alreadySynced"):
                    continue
                orig_val = orig_card.get(field) if orig_card else None
                cur_val = cur_card.get(field)
                if _is_noise(orig_val, cur_val):
                    continue
                if not _deep_equal(orig_val, cur_val):
                    updates.append(create_repeater_update_change(
                        card_name="PowerOfAttorney",
                        client_number=client,
                        section_name="poa",
                        item=attorney_item,
                        field_name=field,
                        val=cur_val,
                        old_val=orig_val,
                        meeting_id=meeting_id,
                    ))

    return creates, updates


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def _should_filter(change: dict) -> bool:
    slag = change.get("slag", "")
    if slag in (
        "PersonalDetails.Client1.isThisYourCorrespondenceAddress",
        "PersonalDetails.Client2.isThisYourCorrespondenceAddress",
    ):
        return True
    if slag.lower().endswith(".fullname"):
        return True
    return False


# ---------------------------------------------------------------------------
# Public: generate all changes
# ---------------------------------------------------------------------------

def generate_all_changes(
    original: dict[str, Any],
    current: dict[str, Any],
    meeting_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Produce (create_changes, update_changes) between *original* and *current*.

    Mirrors ``generateAllChanges()`` in diffEngine.js.
    """
    all_creates: list[dict] = []
    all_updates: list[dict] = []

    # Simple cards (skip WillArrangements — handled separately)
    for card in SIMPLE_CARDS:
        if card == "WillArrangements":
            continue
        all_updates.extend(diff_simple_card(original, current, card, meeting_id))

    # WillArrangements
    wa_c, wa_u = diff_will_arrangements(original, current, meeting_id)
    all_creates.extend(wa_c)
    all_updates.extend(wa_u)

    # Repeater cards (skip PowerOfAttorney — handled via WillArrangements)
    for card in REPEATER_CARDS:
        if card == "PowerOfAttorney":
            continue
        c, u = diff_repeater_card(original, current, card, meeting_id)
        all_creates.extend(c)
        all_updates.extend(u)

    # IncomeExpenses
    ie_c, ie_u = diff_income_expenses(original, current, meeting_id)
    all_creates.extend(ie_c)
    all_updates.extend(ie_u)

    # Notes & ClientNeeds
    all_updates.extend(_diff_keyed_card(original, current, "Notes", meeting_id))
    all_updates.extend(_diff_keyed_card(original, current, "ClientNeeds", meeting_id))

    # Filter
    all_creates = [c for c in all_creates if not _should_filter(c)]
    all_updates = [u for u in all_updates if not _should_filter(u)]

    return all_creates, all_updates
