"""Sanitize raw production change objects for replay against staging.

Handles two concerns:
1. Strip isAutomated from formData (causes backend "Missing Mapping" errors)
2. Replace PII values in formData with synthetic values
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


# PII fields to replace in formData (mirrors sanitizer.py values)
_PII_REPLACEMENTS: dict[str, Any] = {
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
    "attorneyFirstName": "TestAttorneyFirst",
    "attorneyLastName": "TestAttorneyLast",
    "attorneyEmail": "test.attorney@example.com",
    "attorneyTelephone": "+44 7700 900001",
    "attorneyAddress": {
        "line1": "2 Test Street",
        "city": "TestCity",
        "postCode": "TE1 2ST",
    },
    "dependentFirstName": "TestFirst",
    "dependentLastName": "TestLast",
    "jobTitle": "Test Job Title",
}

# Metadata fields to strip from formData
_STRIP_FROM_FORMDATA = {"isAutomated"}


def sanitize_change(change: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a single change object: strip isAutomated, replace PII."""
    c = deepcopy(change)
    fd = c.get("formData")
    if not fd:
        return c

    # Strip metadata that must never appear in sync payloads
    for field in _STRIP_FROM_FORMDATA:
        fd.pop(field, None)

    # Replace PII values
    for field, synthetic in _PII_REPLACEMENTS.items():
        if field in fd:
            fd[field] = deepcopy(synthetic)

    return c


def sanitize_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize a list of change objects."""
    return [sanitize_change(c) for c in changes]
