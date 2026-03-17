"""Phase 5: Verify — re-pull the meeting and compare DCJSONs field-by-field."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from .constants import (
    INCOME_EXPENSES_SECTIONS,
    REPEATER_SECTION_MAP,
    SIMPLE_CARDS,
    SKIP_SIMPLE_CARD_FIELDS,
    SKIP_REPEATER_FIELDS,
)

console = Console()

# Fields we never compare (internal, PII-replaced, or auto-filtered)
_SKIP_COMPARE = SKIP_SIMPLE_CARD_FIELDS | {
    "fullName",
    "correspondenceAddress",
    "isThisYourCorrespondenceAddress",
    # Local UUID cross-references: remapped during sanitization, not synced to SF
    "poaInfoId",
    "poaAttorneyId",
}

# PII fields that were replaced with synthetic values — skip in comparison
_PII_FIELDS = {
    "middleName", "nickname", "dateOfBirth", "nationalInsuranceNumber",
    "maidenName", "telephone1", "email2", "homeAddress",
    "dependentFirstName", "dependentLastName",
    "attorneyFirstName", "attorneyLastName", "attorneyEmail",
    "attorneyTelephone", "attorneyAddress",
    "jobTitle",
}


def _is_internal(key: str) -> bool:
    return key.startswith("_")


def _deep_equal(a: Any, b: Any) -> bool:
    if a is b:
        return True
    if a is None or b is None:
        return a is b
    if type(a) is not type(b):
        # Allow int/float comparison
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
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


# ---------------------------------------------------------------------------
# Simple card comparison
# ---------------------------------------------------------------------------

def _compare_simple_card(
    expected: dict, actual: dict, card_name: str,
    mismatches: list[dict], matched: list[str], skipped: list[str],
) -> None:
    for client in ("Client1", "Client2"):
        exp = (expected.get(card_name) or {}).get(client)
        act = (actual.get(card_name) or {}).get(client)
        if not exp:
            continue
        if not act:
            mismatches.append({
                "path": f"{card_name}.{client}",
                "issue": "Missing entire client section in re-pulled data",
            })
            continue

        for field in exp:
            if _is_internal(field) or field in _SKIP_COMPARE or field in _PII_FIELDS:
                skipped.append(f"{card_name}.{client}.{field}")
                continue
            exp_val = exp[field]
            act_val = act.get(field)
            if _deep_equal(exp_val, act_val):
                matched.append(f"{card_name}.{client}.{field}")
            else:
                mismatches.append({
                    "path": f"{card_name}.{client}.{field}",
                    "expected": exp_val,
                    "actual": act_val,
                })


# ---------------------------------------------------------------------------
# Repeater card comparison — match items by data fingerprint
# ---------------------------------------------------------------------------

def _item_fingerprint(item: dict, ignore: set[str] | None = None) -> str:
    """Create a fingerprint from non-internal, non-PII fields for matching."""
    ignore = ignore or set()
    parts: list[str] = []
    for k in sorted(item):
        if _is_internal(k) or k in SKIP_REPEATER_FIELDS or k in _PII_FIELDS or k in ignore:
            continue
        parts.append(f"{k}={item[k]!r}")
    return "|".join(parts)


def _compare_repeater(
    expected: dict, actual: dict, card_name: str, section: str,
    mismatches: list[dict], matched: list[str], skipped: list[str],
) -> None:
    for client in ("Client1", "Client2"):
        exp_items = (expected.get(card_name) or {}).get(client, {}).get(section, [])
        act_items = (actual.get(card_name) or {}).get(client, {}).get(section, [])

        if not exp_items:
            continue

        if len(exp_items) != len(act_items):
            mismatches.append({
                "path": f"{card_name}.{client}.{section}",
                "issue": f"Item count mismatch: expected {len(exp_items)}, got {len(act_items)}",
            })

        # Build fingerprint index for actual items
        act_fps: dict[str, dict] = {}
        for it in act_items:
            fp = _item_fingerprint(it)
            act_fps[fp] = it

        for exp_item in exp_items:
            fp = _item_fingerprint(exp_item)
            act_item = act_fps.get(fp)
            if not act_item:
                mismatches.append({
                    "path": f"{card_name}.{client}.{section}",
                    "issue": f"No matching item found for fingerprint (id={exp_item.get('id', '?')[:8]}…)",
                })
                continue

            # Compare syncable fields
            for field in exp_item:
                if _is_internal(field) or field in SKIP_REPEATER_FIELDS or field in _PII_FIELDS:
                    skipped.append(f"{card_name}.{client}.{section}[].{field}")
                    continue
                if _deep_equal(exp_item[field], act_item.get(field)):
                    matched.append(f"{card_name}.{client}.{section}[].{field}")
                else:
                    mismatches.append({
                        "path": f"{card_name}.{client}.{section}[].{field}",
                        "expected": exp_item[field],
                        "actual": act_item.get(field),
                    })


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def verify(
    expected_dcjson: dict[str, Any],
    actual_dcjson: dict[str, Any],
) -> dict[str, Any]:
    """Compare expected (sanitized) vs actual (re-pulled) DCJSONs.

    Returns a report dict with keys: matched, mismatches, skipped.
    """
    mismatches: list[dict] = []
    matched: list[str] = []
    skipped: list[str] = []

    # Simple cards
    for card in SIMPLE_CARDS:
        _compare_simple_card(expected_dcjson, actual_dcjson, card, mismatches, matched, skipped)

    # Notes & ClientNeeds
    for card in ("Notes", "ClientNeeds"):
        _compare_simple_card(expected_dcjson, actual_dcjson, card, mismatches, matched, skipped)

    # Repeater cards
    for card, section in REPEATER_SECTION_MAP.items():
        _compare_repeater(expected_dcjson, actual_dcjson, card, section, mismatches, matched, skipped)

    # IncomeExpenses
    for section in INCOME_EXPENSES_SECTIONS:
        _compare_repeater(
            expected_dcjson, actual_dcjson,
            "IncomeExpenses", section,
            mismatches, matched, skipped,
        )

    return {"matched": matched, "mismatches": mismatches, "skipped": skipped}


def print_report(report: dict[str, Any]) -> None:
    """Pretty-print the verification report."""
    matched = report["matched"]
    mismatches = report["mismatches"]
    skipped = report["skipped"]

    console.print(f"\n[bold]Verification Report[/bold]")
    console.print(f"  Matched:    [green]{len(matched)}[/green]")
    console.print(f"  Mismatches: [red]{len(mismatches)}[/red]")
    console.print(f"  Skipped:    [dim]{len(skipped)}[/dim]")

    if mismatches:
        console.print("\n[bold red]Mismatches:[/bold red]")
        table = Table()
        table.add_column("Path")
        table.add_column("Issue / Expected")
        table.add_column("Actual")

        for m in mismatches[:50]:  # Cap display
            issue = m.get("issue", "")
            if issue:
                table.add_row(m["path"], issue, "")
            else:
                table.add_row(
                    m["path"],
                    str(m.get("expected", ""))[:80],
                    str(m.get("actual", ""))[:80],
                )
        console.print(table)

        if len(mismatches) > 50:
            console.print(f"  … and {len(mismatches) - 50} more")
    else:
        console.print("\n[bold green]All syncable fields match![/bold green]")
