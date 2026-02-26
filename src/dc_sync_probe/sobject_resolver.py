"""SF object resolver — determines the correct Salesforce object type(s) for items.

Mirrors sObjectResolver.js from dcReact.
"""

from __future__ import annotations

from typing import Any

from .constants import (
    ASSET_CATEGORIES,
    BANK_CATEGORIES,
    FAMILY_SOBJECTS,
    INCOME_EXPENSES_SECTIONS,
    INVESTMENT_CATEGORIES,
    LIABILITY_CATEGORIES,
    SF_ASSETS_AND_LIABILITIES,
    SF_FINANCIAL_ACCOUNT,
    SF_FINANCIAL_ACCOUNT_ROLE,
)


def is_joint_item(item: dict[str, Any]) -> bool:
    """Check if an item is joint (owned by both clients)."""
    owner = item.get("owner")
    return owner == "Joint" or (isinstance(owner, list) and len(owner) == 2)


def _is_asset_with_sync_markers(item: dict[str, Any]) -> bool:
    """True if item has needsSync or comesFrom == AssetsAndLiabilities."""
    return bool(item.get("needsSync")) or item.get("comesFrom") == SF_ASSETS_AND_LIABILITIES


def _is_financial_asset(item: dict[str, Any]) -> bool:
    """Check if an asset uses FinServ__FinancialAccount__c (investment or bank)."""
    cat = item.get("category", "")
    # "Other Assets" is investment ONLY when it doesn't have sync markers
    if cat in ASSET_CATEGORIES and _is_asset_with_sync_markers(item):
        return False
    return cat in INVESTMENT_CATEGORIES or cat in BANK_CATEGORIES


def _is_financial_liability(item: dict[str, Any]) -> bool:
    """Check if a liability is a mortgage (anything not in LIABILITY_CATEGORIES)."""
    lt = item.get("liabilityType", "")
    if not lt:
        return True  # default to mortgage if no type
    if lt in LIABILITY_CATEGORIES and item.get("comesFrom") != SF_FINANCIAL_ACCOUNT:
        return False
    return lt not in LIABILITY_CATEGORIES


def needs_create(item: dict[str, Any]) -> bool:
    """An item needs CREATE when it has no comesFrom."""
    return not item.get("comesFrom")


def get_sobject_names(
    card_name: str,
    section_name: str,
    item: dict[str, Any],
) -> list[str]:
    """Return SF object name(s) for a repeater item.

    Family and joint financial objects return 2 names; others return 1.
    """
    # Family → ContactAccount + ContactRelation
    if card_name == "Family":
        return list(FAMILY_SOBJECTS)

    # PowerOfAttorney
    if card_name == "PowerOfAttorney":
        if section_name == "poaInfo":
            return ["Account"]
        return list(FAMILY_SOBJECTS)  # poa: ContactAccount + ContactRelation

    joint = is_joint_item(item)

    # Assets
    if card_name == "Assets":
        if _is_financial_asset(item):
            return [SF_FINANCIAL_ACCOUNT, SF_FINANCIAL_ACCOUNT_ROLE] if joint else [SF_FINANCIAL_ACCOUNT]
        return [SF_ASSETS_AND_LIABILITIES]

    # Liabilities
    if card_name == "Liabilities":
        if _is_financial_liability(item):
            return [SF_FINANCIAL_ACCOUNT, SF_FINANCIAL_ACCOUNT_ROLE] if joint else [SF_FINANCIAL_ACCOUNT]
        return [SF_ASSETS_AND_LIABILITIES]

    # Pensions / Protections — all financial
    if card_name in ("Pensions", "Protections"):
        return [SF_FINANCIAL_ACCOUNT, SF_FINANCIAL_ACCOUNT_ROLE] if joint else [SF_FINANCIAL_ACCOUNT]

    # IncomeExpenses
    if card_name == "IncomeExpenses":
        so = INCOME_EXPENSES_SECTIONS.get(section_name)
        return [so] if so else []

    return []
