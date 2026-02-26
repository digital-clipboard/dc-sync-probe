"""Shared test fixtures — realistic DCJSON structures for all test modules."""

from __future__ import annotations

import uuid
from copy import deepcopy

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Minimal but realistic DCJSON fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client1_personal_details():
    return {
        "id": _uuid(),
        "firstName": "Ann",
        "lastName": "Noble",
        "middleName": "Marie",
        "nickname": "Annie",
        "dateOfBirth": "1980-05-15",
        "nationalInsuranceNumber": "AB123456C",
        "maidenName": "Smith",
        "telephone1": "+44 7700 123456",
        "email1": "ann@example.com",
        "email2": "ann.other@example.com",
        "homeAddress": {
            "line1": "10 Real Street",
            "city": "London",
            "postCode": "SW1A 1AA",
        },
        "fullName": "Ann Marie Noble",
        "correspondenceAddress": {"line1": "same"},
        "isThisYourCorrespondenceAddress": True,
        "dirty": False,
        "hasData": True,
        "notApplicable": False,
        "_SF": {"sfId": "003xx0000001"},
    }


@pytest.fixture()
def client2_personal_details():
    return {
        "id": _uuid(),
        "firstName": "David",
        "lastName": "Noble",
        "middleName": "James",
        "nickname": "Dave",
        "dateOfBirth": "1978-03-20",
        "nationalInsuranceNumber": "CD789012E",
        "maidenName": "",
        "telephone1": "+44 7700 654321",
        "email1": "david@example.com",
        "email2": "david.other@example.com",
        "homeAddress": {
            "line1": "10 Real Street",
            "city": "London",
            "postCode": "SW1A 1AA",
        },
        "fullName": "David James Noble",
        "dirty": False,
        "hasData": True,
        "_SF": {"sfId": "003xx0000002"},
    }


@pytest.fixture()
def asset_item_financial():
    """A financial asset (ISA) — uses FinServ__FinancialAccount__c."""
    return {
        "id": _uuid(),
        "category": "ISAs",
        "typeOfAssetInvestment": "Stocks and Shares ISA",
        "provider": "Hargreaves Lansdown",
        "status": "Active",
        "value": 50000,
        "valuationDate": "2025-01-01",
        "owner": "Client1",
        "comesFrom": "FinServ__FinancialAccount__c",
        "_SF": {"sfId": "fin_001"},
        "needsSync": False,
    }


@pytest.fixture()
def asset_item_property():
    """A property asset (Personal Assets) — uses FinServ__AssetsAndLiabilities__c."""
    return {
        "id": _uuid(),
        "category": "Personal Assets",
        "typeOfAssetInvestment": "Property",
        "value": 500000,
        "valuationDate": "2025-01-01",
        "owner": "Joint",
        "comesFrom": "FinServ__AssetsAndLiabilities__c",
        "_SF": {"sfId": "asset_001"},
        "needsSync": False,
    }


@pytest.fixture()
def asset_item_new():
    """A new financial asset (no comesFrom) — needs CREATE."""
    return {
        "id": _uuid(),
        "category": "ISAs",
        "typeOfAssetInvestment": "Cash ISA",
        "provider": "Vanguard",
        "status": "Active",
        "value": 20000,
        "owner": "Client1",
    }


@pytest.fixture()
def liability_mortgage():
    """A mortgage liability — financial (not in LIABILITY_CATEGORIES)."""
    return {
        "id": _uuid(),
        "liabilityType": "Mortgage",
        "nameOfLender": "Halifax",
        "status": "Active",
        "outstandingBalance": 200000,
        "owner": "Joint",
        "comesFrom": "FinServ__FinancialAccount__c",
        "_SF": {"sfId": "lia_001"},
    }


@pytest.fixture()
def liability_personal():
    """A personal debt — non-financial (in LIABILITY_CATEGORIES)."""
    return {
        "id": _uuid(),
        "liabilityType": "Personal Debt/Liability",
        "outstandingBalance": 5000,
        "owner": "Client1",
        "comesFrom": "FinServ__AssetsAndLiabilities__c",
        "_SF": {"sfId": "lia_002"},
    }


@pytest.fixture()
def family_item():
    return {
        "id": _uuid(),
        "relationship": "Son",
        "dependentFirstName": "Tom",
        "dependentLastName": "Noble",
        "owner": "Client1",
        "comesFrom": "ContactAccount",
        "_SF": {"sfId": "fam_001"},
    }


@pytest.fixture()
def family_item_new():
    return {
        "id": _uuid(),
        "relationship": "Daughter",
        "dependentFirstName": "Emily",
        "dependentLastName": "Noble",
        "owner": "Client1",
    }


@pytest.fixture()
def pension_item():
    return {
        "id": _uuid(),
        "pensionType": "Defined Contribution",
        "provider": "Aviva",
        "status": "Active",
        "owner": "Client1",
        "comesFrom": "FinServ__FinancialAccount__c",
        "_SF": {"sfId": "pen_001"},
    }


@pytest.fixture()
def protection_item():
    return {
        "id": _uuid(),
        "protectionType": "Life Cover",
        "provider": "Legal & General",
        "status": "Active",
        "owner": "Client2",
        "comesFrom": "FinServ__FinancialAccount__c",
        "_SF": {"sfId": "prot_001"},
    }


@pytest.fixture()
def income_item():
    return {
        "id": _uuid(),
        "category": "Employment",
        "amount": {
            "amount": {
                "amountGBP": 50000,
                "amountConverted": "£50,000.00",
                "amountMasked": "£50,000.00",
            },
        },
        "owner": "Client1",
        "comesFrom": "Income__c",
        "_SF": {"sfId": "inc_001"},
    }


@pytest.fixture()
def income_item_joint():
    """A joint income item — should be split when creating."""
    return {
        "id": _uuid(),
        "category": "Rental Income",
        "amount": {
            "amount": {
                "amountGBP": 24000,
                "amountConverted": "£24,000.00",
                "amountMasked": "£24,000.00",
            },
        },
        "owner": "Joint",
    }


@pytest.fixture()
def employment_item():
    return {
        "id": _uuid(),
        "employmentStatus": "Employed",
        "jobTitle": "Software Engineer",
        "nameOfTheCompany": "TechCo",
        "occupation": "IT",
        "owner": "Client1",
        "comesFrom": "Account",
        "_SF": {"sfId": "emp_001"},
    }


@pytest.fixture()
def will_arrangements_with_poa():
    """WillArrangements card with merged POA data."""
    return {
        "id": _uuid(),
        "hasWill": True,
        "willUpToDate": True,
        "powerOfAttoneyType": "Lasting",
        "powerOfAttoneyInvoked": "No",
        "powerOfAttoneyInvokedDate": "",
        "poaInfoId": _uuid(),
        "poaInfo_SF": {"sfId": "poa_info_001"},
        "attorneyFirstName": "Jane",
        "attorneyLastName": "Smith",
        "attorneyEmail": "jane@example.com",
        "attorneyTelephone": "+44 7700 000001",
        "attorneyAddress": {"line1": "5 Law St", "city": "London"},
        "alreadySynced": True,
        "poaAttorneyId": _uuid(),
        "poaAttorney_SF": {"sfId": "poa_att_001"},
        "owner": "Client1",
        "dirty": False,
        "hasData": True,
        "_SF": {"sfId": "will_001"},
    }


# ---------------------------------------------------------------------------
# Full DCJSON builders
# ---------------------------------------------------------------------------

@pytest.fixture()
def single_client_dcjson(client1_personal_details, asset_item_financial, family_item, income_item, employment_item):
    """Minimal single-client DCJSON."""
    return {
        "PersonalDetails": {
            "Client1": client1_personal_details,
        },
        "Assets": {
            "Client1": {"assets": [asset_item_financial]},
        },
        "Liabilities": {"Client1": {"liabilities": []}},
        "Family": {
            "Client1": {"family": [family_item]},
        },
        "Pensions": {"Client1": {"pensions": []}},
        "Protections": {"Client1": {"protections": []}},
        "IncomeExpenses": {
            "Client1": {
                "income": [income_item],
                "expenditure": [],
                "emergencyFunding": [],
                "employment": [employment_item],
            },
        },
        "TaxAndResidency": {"Client1": {"taxResident": "UK", "_SF": {"sfId": "tax_001"}}},
        "ClientAssistance": {"Client1": {"needsAssistance": False, "_SF": {"sfId": "ca_001"}}},
        "Disclosure": {"Client1": {"disclosed": True, "_SF": {"sfId": "dis_001"}}},
        "WillArrangements": {"Client1": {"hasWill": True, "_SF": {"sfId": "will_001"}}},
        "Loa": {"Client1": {"loaSigned": True, "_SF": {"sfId": "loa_001"}}},
        "Health": {"Client1": {"inGoodHealth": True, "_SF": {"sfId": "health_001"}}},
        "Notes": {"Client1": {"notes": "Some notes"}},
        "ClientNeeds": {"Client1": {"needs": "Retirement planning"}},
        "PowerOfAttorney": {"Client1": {"poaInfo": [], "poa": []}},
    }


@pytest.fixture()
def joint_dcjson(
    client1_personal_details, client2_personal_details,
    asset_item_financial, asset_item_property,
    liability_mortgage, family_item,
    income_item, income_item_joint, employment_item,
    pension_item, protection_item,
    will_arrangements_with_poa,
):
    """Joint (two-client) DCJSON with data across all cards."""
    return {
        "PersonalDetails": {
            "Client1": client1_personal_details,
            "Client2": client2_personal_details,
        },
        "Assets": {
            "Client1": {"assets": [asset_item_financial, asset_item_property]},
        },
        "Liabilities": {
            "Client1": {"liabilities": [liability_mortgage]},
        },
        "Family": {
            "Client1": {"family": [family_item]},
        },
        "Pensions": {
            "Client1": {"pensions": [pension_item]},
        },
        "Protections": {
            "Client1": {"protections": [protection_item]},
        },
        "IncomeExpenses": {
            "Client1": {
                "income": [income_item, income_item_joint],
                "expenditure": [],
                "emergencyFunding": [],
                "employment": [employment_item],
            },
        },
        "TaxAndResidency": {
            "Client1": {"taxResident": "UK", "_SF": {"sfId": "tax_c1"}},
            "Client2": {"taxResident": "UK", "_SF": {"sfId": "tax_c2"}},
        },
        "ClientAssistance": {
            "Client1": {"needsAssistance": False, "_SF": {"sfId": "ca_c1"}},
        },
        "Disclosure": {
            "Client1": {"disclosed": True, "_SF": {"sfId": "dis_c1"}},
        },
        "WillArrangements": {
            "Client1": will_arrangements_with_poa,
        },
        "Loa": {"Client1": {"loaSigned": True, "_SF": {"sfId": "loa_c1"}}},
        "Health": {
            "Client1": {"inGoodHealth": True, "_SF": {"sfId": "h_c1"}},
            "Client2": {"inGoodHealth": False, "_SF": {"sfId": "h_c2"}},
        },
        "Notes": {"Client1": {"notes": "Joint notes"}},
        "ClientNeeds": {"Client1": {"needs": "Retirement"}},
        "PowerOfAttorney": {
            "Client1": {
                "poaInfo": [{
                    "id": will_arrangements_with_poa["poaInfoId"],
                    "powerOfAttoneyType": "Lasting",
                    "powerOfAttoneyInvoked": "No",
                    "powerOfAttoneyInvokedDate": "",
                    "owner": "Client1",
                    "_SF": {"sfId": "poa_info_001"},
                }],
                "poa": [{
                    "id": will_arrangements_with_poa["poaAttorneyId"],
                    "attorneyFirstName": "Jane",
                    "attorneyLastName": "Smith",
                    "attorneyEmail": "jane@example.com",
                    "attorneyTelephone": "+44 7700 000001",
                    "attorneyAddress": {"line1": "5 Law St", "city": "London"},
                    "owner": "Client1",
                    "comesFrom": "ContactAccount",
                    "_SF": {"sfId": "poa_att_001"},
                }],
            },
        },
    }


@pytest.fixture()
def fresh_dcjson(single_client_dcjson):
    """A 'fresh' DCJSON (as pulled from SF) — used as reference for sanitization."""
    d = deepcopy(single_client_dcjson)
    # Fresh meeting has the real SF-side names
    d["PersonalDetails"]["Client1"]["firstName"] = "Ann"
    d["PersonalDetails"]["Client1"]["lastName"] = "Noble"
    d["PersonalDetails"]["Client1"]["email1"] = "ann.real@sjp.co.uk"
    return d


MEETING_ID = "test-meeting-00000000-0000-0000-0000-000000000001"
