"""Tests for diff_engine.py — the core diff logic generating CREATE + UPDATE changes."""

import uuid
from copy import deepcopy

import pytest

from dc_sync_probe.diff_engine import (
    _deep_equal,
    _is_empty,
    _is_noise,
    _should_filter,
    _split_joint_item,
    diff_income_expenses,
    diff_repeater_card,
    diff_simple_card,
    diff_will_arrangements,
    generate_all_changes,
)

MEETING_ID = "test-meeting-id"


# ---------------------------------------------------------------------------
# Value comparison helpers
# ---------------------------------------------------------------------------

class TestIsEmpty:
    def test_none(self):
        assert _is_empty(None) is True

    def test_empty_string(self):
        assert _is_empty("") is True

    def test_false(self):
        assert _is_empty(False) is True

    def test_zero(self):
        assert _is_empty(0) is True

    def test_empty_list(self):
        assert _is_empty([]) is True

    def test_empty_dict(self):
        assert _is_empty({}) is True

    def test_non_empty_string(self):
        assert _is_empty("hello") is False

    def test_non_zero_number(self):
        assert _is_empty(42) is False

    def test_non_empty_list(self):
        assert _is_empty([1]) is False


class TestIsNoise:
    def test_none_to_empty_string(self):
        assert _is_noise(None, "") is True

    def test_none_to_none(self):
        assert _is_noise(None, None) is True

    def test_both_empty(self):
        assert _is_noise("", False) is True

    def test_none_to_value(self):
        assert _is_noise(None, "hello") is False

    def test_value_to_value(self):
        assert _is_noise("old", "new") is False


class TestDeepEqual:
    def test_same_primitives(self):
        assert _deep_equal("a", "a") is True
        assert _deep_equal(42, 42) is True

    def test_different_primitives(self):
        assert _deep_equal("a", "b") is False

    def test_none_handling(self):
        assert _deep_equal(None, None) is True
        assert _deep_equal(None, "") is False

    def test_dict_equal(self):
        assert _deep_equal({"a": 1, "b": 2}, {"a": 1, "b": 2}) is True

    def test_dict_not_equal(self):
        assert _deep_equal({"a": 1}, {"a": 2}) is False

    def test_nested_dict(self):
        assert _deep_equal(
            {"a": {"b": [1, 2]}},
            {"a": {"b": [1, 2]}},
        ) is True

    def test_list_equal(self):
        assert _deep_equal([1, 2, 3], [1, 2, 3]) is True

    def test_list_not_equal(self):
        assert _deep_equal([1, 2], [1, 3]) is False

    def test_type_mismatch(self):
        assert _deep_equal("1", 1) is False


# ---------------------------------------------------------------------------
# Simple card diff
# ---------------------------------------------------------------------------

class TestDiffSimpleCard:
    def test_detects_field_change(self):
        original = {
            "TaxAndResidency": {
                "Client1": {"taxResident": "UK", "_SF": {"sfId": "tax_001"}},
            },
        }
        current = {
            "TaxAndResidency": {
                "Client1": {"taxResident": "US", "_SF": {"sfId": "tax_001"}},
            },
        }
        changes = diff_simple_card(original, current, "TaxAndResidency", MEETING_ID)
        assert len(changes) == 1
        assert changes[0]["fieldName"] == "taxResident"
        assert changes[0]["val"] == "US"
        assert changes[0]["oldVal"] == "UK"
        assert changes[0]["op"] == "update"

    def test_no_changes_when_equal(self):
        card = {"TaxAndResidency": {"Client1": {"taxResident": "UK", "_SF": {}}}}
        changes = diff_simple_card(card, deepcopy(card), "TaxAndResidency", MEETING_ID)
        assert changes == []

    def test_skips_internal_fields(self):
        original = {"Health": {"Client1": {"_SF": {"a": 1}, "inGoodHealth": True}}}
        current = {"Health": {"Client1": {"_SF": {"a": 2}, "inGoodHealth": True}}}
        changes = diff_simple_card(original, current, "Health", MEETING_ID)
        assert changes == []

    def test_skips_dirty_hasdata(self):
        original = {"Health": {"Client1": {"dirty": False, "hasData": True, "val": "a"}}}
        current = {"Health": {"Client1": {"dirty": True, "hasData": False, "val": "a"}}}
        changes = diff_simple_card(original, current, "Health", MEETING_ID)
        assert changes == []

    def test_noise_filtered(self):
        original = {"Health": {"Client1": {"field1": None}}}
        current = {"Health": {"Client1": {"field1": ""}}}
        changes = diff_simple_card(original, current, "Health", MEETING_ID)
        assert changes == []

    def test_handles_missing_original_card(self):
        """If original doesn't have the card, all current fields are changes."""
        current = {"Health": {"Client1": {"inGoodHealth": True}}}
        changes = diff_simple_card({}, current, "Health", MEETING_ID)
        assert len(changes) == 1

    def test_both_clients(self):
        original = {
            "Health": {
                "Client1": {"inGoodHealth": True, "_SF": {}},
                "Client2": {"inGoodHealth": True, "_SF": {}},
            },
        }
        current = {
            "Health": {
                "Client1": {"inGoodHealth": False, "_SF": {}},
                "Client2": {"inGoodHealth": False, "_SF": {}},
            },
        }
        changes = diff_simple_card(original, current, "Health", MEETING_ID)
        assert len(changes) == 2
        clients = {c["path"][1] for c in changes}
        assert clients == {"Client1", "Client2"}


# ---------------------------------------------------------------------------
# Repeater card diff
# ---------------------------------------------------------------------------

class TestDiffRepeaterCard:
    def test_create_new_item(self):
        original = {"Assets": {"Client1": {"assets": []}}, "PersonalDetails": {}}
        new_item = {
            "id": str(uuid.uuid4()),
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "Vanguard",
            "status": "Active",
            "owner": "Client1",
        }
        current = {
            "Assets": {"Client1": {"assets": [new_item]}},
            "PersonalDetails": {},
        }
        creates, updates = diff_repeater_card(original, current, "Assets", MEETING_ID)
        assert len(creates) >= 1
        assert all(c["op"] == "create" for c in creates)
        assert updates == []

    def test_update_existing_item(self):
        item_id = str(uuid.uuid4())
        orig_item = {
            "id": item_id,
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "Vanguard",
            "status": "Active",
            "value": 50000,
            "owner": "Client1",
            "comesFrom": "FinServ__FinancialAccount__c",
            "_SF": {"sfId": "fin_001"},
        }
        cur_item = {**orig_item, "value": 55000}

        original = {"Assets": {"Client1": {"assets": [orig_item]}}, "PersonalDetails": {}}
        current = {"Assets": {"Client1": {"assets": [cur_item]}}, "PersonalDetails": {}}

        creates, updates = diff_repeater_card(original, current, "Assets", MEETING_ID)
        assert creates == []
        assert len(updates) == 1
        assert updates[0]["fieldName"] == "value"
        assert updates[0]["val"] == 55000
        assert updates[0]["oldVal"] == 50000

    def test_skips_item_without_mandatory_fields(self):
        """New item missing mandatory fields should be skipped."""
        item = {
            "id": str(uuid.uuid4()),
            "category": "",  # missing mandatory
            "owner": "Client1",
        }
        original = {"Assets": {"Client1": {"assets": []}}, "PersonalDetails": {}}
        current = {"Assets": {"Client1": {"assets": [item]}}, "PersonalDetails": {}}

        creates, updates = diff_repeater_card(original, current, "Assets", MEETING_ID)
        assert creates == []

    def test_skips_repeater_metadata_fields(self):
        """Fields like comesFrom, needsSync should not produce update changes."""
        item_id = str(uuid.uuid4())
        orig = {
            "id": item_id, "relationship": "Son", "dependentLastName": "N",
            "owner": "Client1", "comesFrom": "ContactAccount", "_SF": {},
        }
        cur = {
            "id": item_id, "relationship": "Son", "dependentLastName": "N",
            "owner": "Client1", "comesFrom": "ContactAccount", "_SF": {},
            "needsSync": True,
        }
        original = {"Family": {"Client1": {"family": [orig]}}, "PersonalDetails": {}}
        current = {"Family": {"Client1": {"family": [cur]}}, "PersonalDetails": {}}

        creates, updates = diff_repeater_card(original, current, "Family", MEETING_ID)
        assert creates == []
        assert updates == []


# ---------------------------------------------------------------------------
# IncomeExpenses diff with joint splitting
# ---------------------------------------------------------------------------

class TestDiffIncomeExpenses:
    def test_joint_income_split(self):
        """Joint income item → 2 CREATE changes with half amounts."""
        joint_item = {
            "id": str(uuid.uuid4()),
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
        original = {"IncomeExpenses": {"Client1": {"income": []}}, "PersonalDetails": {}}
        current = {
            "IncomeExpenses": {"Client1": {"income": [joint_item]}},
            "PersonalDetails": {},
        }
        creates, updates = diff_income_expenses(original, current, MEETING_ID)
        # Should produce creates for both Client1 and Client2
        assert len(creates) >= 2
        # Check amounts are halved
        for c in creates:
            if c.get("formData", {}).get("amount"):
                amount = c["formData"]["amount"]["amount"]["amountGBP"]
                assert amount == 12000

    def test_non_joint_income_no_split(self):
        item = {
            "id": str(uuid.uuid4()),
            "category": "Employment",
            "amount": {"amount": {"amountGBP": 50000}},
            "owner": "Client1",
        }
        original = {"IncomeExpenses": {"Client1": {"income": []}}, "PersonalDetails": {}}
        current = {"IncomeExpenses": {"Client1": {"income": [item]}}, "PersonalDetails": {}}
        creates, _ = diff_income_expenses(original, current, MEETING_ID)
        assert len(creates) == 1

    def test_employment_update(self):
        item_id = str(uuid.uuid4())
        orig = {
            "id": item_id, "employmentStatus": "Employed", "jobTitle": "Dev",
            "owner": "Client1", "comesFrom": "Account", "_SF": {},
        }
        cur = {**orig, "jobTitle": "Senior Dev"}
        original = {
            "IncomeExpenses": {"Client1": {"employment": [orig]}},
            "PersonalDetails": {},
        }
        current = {
            "IncomeExpenses": {"Client1": {"employment": [cur]}},
            "PersonalDetails": {},
        }
        creates, updates = diff_income_expenses(original, current, MEETING_ID)
        assert creates == []
        assert len(updates) == 1
        assert updates[0]["fieldName"] == "jobTitle"


class TestSplitJointItem:
    def test_client1_keeps_id(self):
        item = {
            "id": "original-id",
            "owner": "Joint",
            "amount": {"amount": {"amountGBP": 1000, "amountConverted": "£1,000.00", "amountMasked": "£1,000.00"}},
        }
        split = _split_joint_item(item, "Client1")
        assert split["id"] == "original-id"
        assert split["owner"] == "Client1"
        assert split["amount"]["amount"]["amountGBP"] == 500

    def test_client2_gets_new_id(self):
        item = {
            "id": "original-id",
            "owner": "Joint",
            "amount": {"amount": {"amountGBP": 1000, "amountConverted": "£1,000.00", "amountMasked": "£1,000.00"}},
        }
        split = _split_joint_item(item, "Client2")
        assert split["id"] != "original-id"
        uuid.UUID(split["id"])  # valid UUID
        assert split["owner"] == "Client2"
        assert split["amount"]["amount"]["amountGBP"] == 500

    def test_odd_amount_rounding(self):
        item = {
            "id": "x",
            "owner": "Joint",
            "amount": {"amount": {"amountGBP": 1001, "amountConverted": "", "amountMasked": ""}},
        }
        split = _split_joint_item(item, "Client1")
        assert split["amount"]["amount"]["amountGBP"] == 500.5


# ---------------------------------------------------------------------------
# WillArrangements diff (POA handling)
# ---------------------------------------------------------------------------

class TestDiffWillArrangements:
    def test_regular_field_change(self):
        original = {
            "WillArrangements": {
                "Client1": {"hasWill": True, "_SF": {}, "id": "w1"},
            },
        }
        current = {
            "WillArrangements": {
                "Client1": {"hasWill": False, "_SF": {}, "id": "w1"},
            },
        }
        creates, updates = diff_will_arrangements(original, current, MEETING_ID)
        assert creates == []
        assert len(updates) == 1
        assert updates[0]["fieldName"] == "hasWill"

    def test_poa_info_produces_repeater_update(self):
        original = {
            "WillArrangements": {
                "Client1": {
                    "powerOfAttoneyType": "Lasting",
                    "powerOfAttoneyInvoked": "No",
                    "poaInfoId": "poa-id",
                    "_SF": {},
                },
            },
        }
        current = {
            "WillArrangements": {
                "Client1": {
                    "powerOfAttoneyType": "Lasting",
                    "powerOfAttoneyInvoked": "Yes",
                    "poaInfoId": "poa-id",
                    "_SF": {},
                },
            },
        }
        creates, updates = diff_will_arrangements(original, current, MEETING_ID)
        poa_updates = [u for u in updates if u["path"][0] == "PowerOfAttorney"]
        assert len(poa_updates) == 1
        assert poa_updates[0]["fieldName"] == "powerOfAttoneyInvoked"
        assert poa_updates[0]["type"] == "repeater"

    def test_new_attorney_creates(self):
        """New attorney (not already synced) → CREATE changes."""
        current = {
            "WillArrangements": {
                "Client1": {
                    "attorneyFirstName": "Jane",
                    "attorneyLastName": "Doe",
                    "alreadySynced": False,
                    "poaAttorneyId": "att-id",
                    "_SF": {},
                },
            },
        }
        creates, updates = diff_will_arrangements({}, current, MEETING_ID)
        assert len(creates) >= 1
        assert all(c["op"] == "create" for c in creates)
        assert creates[0]["path"][0] == "PowerOfAttorney"

    def test_existing_attorney_updates(self):
        """Already synced attorney → UPDATE changes."""
        original = {
            "WillArrangements": {
                "Client1": {
                    "attorneyFirstName": "Jane",
                    "attorneyLastName": "Old",
                    "alreadySynced": True,
                    "poaAttorneyId": "att-id",
                    "poaAttorney_SF": {"sfId": "sf-att"},
                    "_SF": {},
                },
            },
        }
        current = deepcopy(original)
        current["WillArrangements"]["Client1"]["attorneyLastName"] = "New"

        creates, updates = diff_will_arrangements(original, current, MEETING_ID)
        assert creates == []
        poa_updates = [u for u in updates if u["path"][0] == "PowerOfAttorney"]
        assert len(poa_updates) == 1
        assert poa_updates[0]["fieldName"] == "attorneyLastName"


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

class TestShouldFilter:
    def test_filters_correspondence_address(self):
        change = {"slag": "PersonalDetails.Client1.isThisYourCorrespondenceAddress"}
        assert _should_filter(change) is True

    def test_filters_fullname(self):
        change = {"slag": "PersonalDetails.Client1.fullName"}
        assert _should_filter(change) is True

    def test_does_not_filter_normal(self):
        change = {"slag": "PersonalDetails.Client1.middleName"}
        assert _should_filter(change) is False


# ---------------------------------------------------------------------------
# generate_all_changes integration
# ---------------------------------------------------------------------------

class TestGenerateAllChanges:
    def test_no_changes_for_identical(self, single_client_dcjson):
        creates, updates = generate_all_changes(
            single_client_dcjson, deepcopy(single_client_dcjson), MEETING_ID,
        )
        assert creates == []
        assert updates == []

    def test_simple_card_change_in_updates(self):
        original = {
            "Health": {"Client1": {"inGoodHealth": True, "_SF": {}}},
        }
        current = {
            "Health": {"Client1": {"inGoodHealth": False, "_SF": {}}},
        }
        creates, updates = generate_all_changes(original, current, MEETING_ID)
        assert creates == []
        assert len(updates) == 1
        assert updates[0]["fieldName"] == "inGoodHealth"

    def test_new_asset_in_creates(self):
        new_item = {
            "id": str(uuid.uuid4()),
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "Vanguard",
            "status": "Active",
            "owner": "Client1",
        }
        original = {"Assets": {"Client1": {"assets": []}}, "PersonalDetails": {}}
        current = {
            "Assets": {"Client1": {"assets": [new_item]}},
            "PersonalDetails": {},
        }
        creates, updates = generate_all_changes(original, current, MEETING_ID)
        assert len(creates) >= 1
        assert all(c["op"] == "create" for c in creates)

    def test_filters_correspondence_and_fullname(self):
        original = {
            "PersonalDetails": {
                "Client1": {
                    "isThisYourCorrespondenceAddress": True,
                    "fullName": "Old Name",
                    "_SF": {},
                },
            },
        }
        current = {
            "PersonalDetails": {
                "Client1": {
                    "isThisYourCorrespondenceAddress": False,
                    "fullName": "New Name",
                    "_SF": {},
                },
            },
        }
        creates, updates = generate_all_changes(original, current, MEETING_ID)
        assert creates == []
        assert updates == []

    def test_notes_changes(self):
        original = {"Notes": {"Client1": {"notes": "old"}}}
        current = {"Notes": {"Client1": {"notes": "new"}}}
        creates, updates = generate_all_changes(original, current, MEETING_ID)
        assert len(updates) == 1
        assert updates[0]["fieldName"] == "notes"

    def test_client_needs_changes(self):
        original = {"ClientNeeds": {"Client1": {"needs": "old"}}}
        current = {"ClientNeeds": {"Client1": {"needs": "new"}}}
        creates, updates = generate_all_changes(original, current, MEETING_ID)
        assert len(updates) == 1
        assert updates[0]["fieldName"] == "needs"
