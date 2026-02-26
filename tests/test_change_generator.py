"""Tests for change_generator.py — change object creation."""

import pytest

from dc_sync_probe.change_generator import (
    create_repeater_create_changes,
    create_repeater_update_change,
    create_simple_change,
)

MEETING_ID = "test-meeting-id"


class TestCreateSimpleChange:
    def test_structure(self):
        change = create_simple_change(
            card_name="PersonalDetails",
            client_number="Client1",
            field_name="middleName",
            val="NewMiddle",
            old_val="OldMiddle",
            meeting_id=MEETING_ID,
            form_data={"id": "pd-id", "middleName": "NewMiddle"},
        )
        assert change["op"] == "update"
        assert change["type"] == "simple"
        assert change["path"] == ["PersonalDetails", "Client1", "middleName"]
        assert change["slag"] == "PersonalDetails.Client1.middleName"
        assert change["val"] == "NewMiddle"
        assert change["oldVal"] == "OldMiddle"
        assert change["meetingId"] == MEETING_ID
        assert change["fieldName"] == "middleName"
        assert change["syncable"] is True
        assert change["joint"] is False
        assert change["joinedJoint"] is False
        assert "timestamp" in change
        assert change["dcId"] == "pd-id"


class TestCreateRepeaterCreateChanges:
    def test_single_owner_financial(self):
        """Single-owner ISA → 1 change for FinServ__FinancialAccount__c."""
        item = {
            "id": "new-isa",
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "owner": "Client1",
        }
        changes = create_repeater_create_changes(
            card_name="Assets",
            client_number="Client1",
            section_name="assets",
            item=item,
            meeting_id=MEETING_ID,
        )
        assert len(changes) == 1
        c = changes[0]
        assert c["op"] == "create"
        assert c["type"] == "repeater"
        assert c["sObjectName"] == "FinServ__FinancialAccount__c"
        assert c["dcId"] == "new-isa"
        assert c["joint"] is False

    def test_joint_financial_produces_two_changes(self):
        """Joint ISA → 2 changes: Account on Client1, Role on Client2."""
        item = {
            "id": "joint-isa",
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "owner": "Joint",
        }
        changes = create_repeater_create_changes(
            card_name="Assets",
            client_number="Client1",
            section_name="assets",
            item=item,
            meeting_id=MEETING_ID,
        )
        assert len(changes) == 2
        assert changes[0]["sObjectName"] == "FinServ__FinancialAccount__c"
        assert changes[0]["path"][1] == "Client1"
        assert changes[1]["sObjectName"] == "FinServ__FinancialAccountRole__c"
        assert changes[1]["path"][1] == "Client2"
        assert all(c["joint"] is True for c in changes)

    def test_family_produces_contact_relations(self):
        """Family → ContactAccount + ContactRelation."""
        item = {
            "id": "fam-1",
            "relationship": "Son",
            "dependentLastName": "Noble",
            "owner": "Client1",
        }
        changes = create_repeater_create_changes(
            card_name="Family",
            client_number="Client1",
            section_name="family",
            item=item,
            meeting_id=MEETING_ID,
        )
        assert len(changes) == 2
        assert changes[0]["sObjectName"] == "ContactAccount"
        assert changes[0]["path"][1] == "Client1"
        assert changes[1]["sObjectName"] == "FinServ__ContactContactRelation__c"

    def test_joint_family_produces_three_changes(self):
        """Joint Family → ContactAccount on Client1 + ContactRelation on both clients."""
        item = {
            "id": "fam-joint",
            "relationship": "Child",
            "dependentLastName": "Noble",
            "owner": ["Client1", "Client2"],
        }
        changes = create_repeater_create_changes(
            card_name="Family",
            client_number="Client1",
            section_name="family",
            item=item,
            meeting_id=MEETING_ID,
        )
        assert len(changes) == 3
        assert changes[0]["sObjectName"] == "ContactAccount"
        assert changes[1]["sObjectName"] == "FinServ__ContactContactRelation__c"
        assert changes[1]["path"][1] == "Client1"
        assert changes[2]["sObjectName"] == "FinServ__ContactContactRelation__c"
        assert changes[2]["path"][1] == "Client2"

    def test_income_single_change(self):
        item = {"id": "inc-1", "owner": "Client1"}
        changes = create_repeater_create_changes(
            card_name="IncomeExpenses",
            client_number="Client1",
            section_name="income",
            item=item,
            meeting_id=MEETING_ID,
        )
        assert len(changes) == 1
        assert changes[0]["sObjectName"] == "Income__c"


class TestCreateRepeaterUpdateChange:
    def test_structure(self):
        item = {
            "id": "asset-id",
            "category": "ISAs",
            "owner": "Client1",
            "comesFrom": "FinServ__FinancialAccount__c",
        }
        change = create_repeater_update_change(
            card_name="Assets",
            client_number="Client1",
            section_name="assets",
            item=item,
            field_name="value",
            val=60000,
            old_val=50000,
            meeting_id=MEETING_ID,
        )
        assert change["op"] == "update"
        assert change["type"] == "repeater"
        assert change["sObjectName"] == "FinServ__FinancialAccount__c"
        assert change["val"] == 60000
        assert change["oldVal"] == 50000
        assert change["fieldName"] == "value"
        assert change["dcId"] == "asset-id"
        assert change["joint"] is False

    def test_joint_item_path(self):
        item = {
            "id": "joint-asset",
            "category": "ISAs",
            "owner": "Joint",
            "comesFrom": "FinServ__FinancialAccount__c",
        }
        change = create_repeater_update_change(
            card_name="Assets",
            client_number="Client1",
            section_name="assets",
            item=item,
            field_name="value",
            val=100,
            old_val=50,
            meeting_id=MEETING_ID,
        )
        assert change["path"][1] == "Joint"
        assert change["joint"] is True
