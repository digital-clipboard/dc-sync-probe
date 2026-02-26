"""Mandatory field validators per card — mirrors schemaHelpers from dcReact."""

from __future__ import annotations

from typing import Any

from .constants import BANK_CATEGORIES, INVESTMENT_CATEGORIES, LIABILITY_CATEGORIES

# Inactive statuses from financialStatusHelper.js / listData.js
_INACTIVE_STATUSES = {
    "cancelled", "cooled off", "duplicate", "lapsed",
    "npw", "pipeline", "surrendered", "transferred",
}


def _status_inactive(item: dict[str, Any]) -> bool:
    status = item.get("status", "")
    if not status:
        return True
    return status.lower() in _INACTIVE_STATUSES


def _family_mandatory(item: dict[str, Any], _is_two_client: bool) -> bool:
    """Family: needs relationship + dependentLastName."""
    return bool(item.get("relationship") and item.get("dependentLastName"))


def _assets_mandatory(item: dict[str, Any], is_two_client: bool) -> bool:
    """Assets: owner (if two-client), category, typeOfAssetInvestment.
    Financial assets also need provider + status (+ dateClosed if inactive).
    Mirrors assetsHelper.js mandatoryItemsFilled.
    """
    if is_two_client and not item.get("owner"):
        return False
    if not item.get("category") or not item.get("typeOfAssetInvestment"):
        return False
    cat = item.get("category", "")
    is_financial = cat in INVESTMENT_CATEGORIES or cat in BANK_CATEGORIES
    if is_financial:
        if not item.get("provider") or not item.get("status"):
            return False
        if _status_inactive(item) and not item.get("dateClosed"):
            return False
    return True


def _liabilities_mandatory(item: dict[str, Any], is_two_client: bool) -> bool:
    """Liabilities: owner (if two-client), liabilityType.
    Mortgages also need nameOfLender + status (+ dateClosed if inactive).
    Mirrors liabilitiesHelper.js mandatoryItemsFilled.
    """
    if is_two_client and not item.get("owner"):
        return False
    if not item.get("liabilityType"):
        return False
    lt = item.get("liabilityType", "")
    is_mortgage = lt not in LIABILITY_CATEGORIES
    if is_mortgage:
        if not item.get("nameOfLender") or not item.get("status"):
            return False
        if _status_inactive(item) and not item.get("dateClosed"):
            return False
    return True


def _income_expenses_mandatory(item: dict[str, Any], _is_two_client: bool) -> bool:
    """IncomeExpenses: any of amount > 0, emergency funding > 0, or employment fields filled."""
    # Income/expenditure
    amount_obj = item.get("amount")
    if isinstance(amount_obj, dict):
        inner = amount_obj.get("amount", {})
        gbp = inner.get("amountGBP")
        if gbp is not None and gbp > 0:
            return True
    # Emergency funding
    ef = item.get("amountOfEmergencyFunding")
    if isinstance(ef, dict):
        if (ef.get("amountGBP") or 0) > 0:
            return True
    elif isinstance(ef, (int, float)) and ef > 0:
        return True
    # Employment
    for f in ("employmentStatus", "jobTitle", "nameOfTheCompany", "occupation"):
        if item.get(f):
            return True
    return False


def _pensions_mandatory(item: dict[str, Any], is_two_client: bool) -> bool:
    """Pensions: owner (if two-client), typeOfPension, typeOfPlan, nameOfProvider, status.
    Mirrors pensionsHelper.js mandatoryItemsFilled.
    """
    if is_two_client and not item.get("owner"):
        return False
    if not item.get("typeOfPension"):
        return False
    if not item.get("nameOfProvider"):
        return False
    if not item.get("status"):
        return False
    if _status_inactive(item) and not item.get("dateClosed"):
        return False
    # Both Defined Benefit and Money Purchase require typeOfPlan
    return bool(item.get("typeOfPlan"))


def _protections_mandatory(item: dict[str, Any], is_two_client: bool) -> bool:
    """Protections: owner (if two-client), protectionType, nameOfInsuranceCompany, status.
    Mirrors protectionsHelper.js mandatoryItemsFilled.
    """
    if is_two_client and not item.get("owner"):
        return False
    if not item.get("protectionType"):
        return False
    if not item.get("nameOfInsuranceCompany"):
        return False
    if not item.get("status"):
        return False
    if _status_inactive(item) and not item.get("dateClosed"):
        return False
    return True


_CHECKERS: dict[str, Any] = {
    "Family": _family_mandatory,
    "Assets": _assets_mandatory,
    "Liabilities": _liabilities_mandatory,
    "IncomeExpenses": _income_expenses_mandatory,
    "Pensions": _pensions_mandatory,
    "Protections": _protections_mandatory,
}


def has_mandatory_fields_filled(
    item: dict[str, Any],
    card_name: str,
    is_two_client: bool,
) -> bool:
    """Return True if all mandatory fields are present for this item."""
    checker = _CHECKERS.get(card_name)
    if checker is None:
        return True  # No validator → allow
    return checker(item, is_two_client)
