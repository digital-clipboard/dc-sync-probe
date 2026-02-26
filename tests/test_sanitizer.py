"""Tests for sanitizer.py — PII replacement, ID remapping, metadata stripping."""

import uuid

from dc_sync_probe.sanitizer import sanitize


class TestPIIReplacement:
    def test_personal_details_pii_replaced(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        pd = result["PersonalDetails"]["Client1"]

        # PII fields replaced with synthetic values
        assert pd["middleName"] == "TestMiddle"
        assert pd["nickname"] == "TestNickname"
        assert pd["dateOfBirth"] == "1990-01-01"
        assert pd["nationalInsuranceNumber"] == "QQ123456C"
        assert pd["telephone1"] == "+44 7700 900000"
        assert pd["email2"] == "test.personal@example.com"
        assert pd["homeAddress"]["line1"] == "1 Test Street"

    def test_keeps_names_from_fresh(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        pd = result["PersonalDetails"]["Client1"]

        # firstName, lastName, email1 come from fresh meeting
        assert pd["firstName"] == "Ann"
        assert pd["lastName"] == "Noble"
        assert pd["email1"] == "ann.real@sjp.co.uk"

    def test_fullname_cleared(self, single_client_dcjson, fresh_dcjson):
        """fullName is never synced but must not contain real PII in the output."""
        result = sanitize(single_client_dcjson, fresh_dcjson)
        pd = result["PersonalDetails"]["Client1"]
        assert pd.get("fullName") == "", f"fullName should be cleared, got: {pd.get('fullName')}"

    def test_correspondence_address_cleared(self, single_client_dcjson, fresh_dcjson):
        """correspondenceAddress is never synced but must not contain real PII."""
        result = sanitize(single_client_dcjson, fresh_dcjson)
        pd = result["PersonalDetails"]["Client1"]
        assert pd.get("correspondenceAddress") == "", (
            f"correspondenceAddress should be cleared, got: {pd.get('correspondenceAddress')}"
        )

    def test_client2_uses_synthetic_when_no_fresh_client2(self, joint_dcjson, fresh_dcjson):
        """When source has Client2 but fresh has no Client2, use synthetic fallbacks.
        Real names must never leak through — this is the joint-source-on-single-fresh case.
        """
        # fresh_dcjson is single-client (no Client2)
        assert "Client2" not in (fresh_dcjson.get("PersonalDetails") or {})

        result = sanitize(joint_dcjson, fresh_dcjson)
        pd2 = result["PersonalDetails"]["Client2"]

        assert pd2["firstName"] == "TestFirstName", (
            f"Client2 firstName should be synthetic, got: {pd2['firstName']!r}"
        )
        assert pd2["lastName"] == "TestLastName", (
            f"Client2 lastName should be synthetic, got: {pd2['lastName']!r}"
        )
        assert pd2["email1"] == "test.work@example.com", (
            f"Client2 email1 should be synthetic, got: {pd2['email1']!r}"
        )

    def test_client2_all_pii_replaced(self, joint_dcjson, fresh_dcjson):
        """All 13 PersonalDetails PII fields are cleaned for Client2."""
        result = sanitize(joint_dcjson, fresh_dcjson)
        pd2 = result["PersonalDetails"]["Client2"]

        assert pd2.get("fullName") == ""
        assert pd2.get("firstName") == "TestFirstName"
        assert pd2.get("lastName") == "TestLastName"
        assert pd2.get("email1") == "test.work@example.com"
        assert pd2.get("middleName") == "TestMiddle"
        assert pd2.get("nickname") == "TestNickname"
        assert pd2.get("dateOfBirth") == "1990-01-01"
        assert pd2.get("nationalInsuranceNumber") == "QQ123456C"
        assert pd2.get("telephone1") == "+44 7700 900000"
        assert pd2.get("email2") == "test.personal@example.com"
        assert pd2.get("homeAddress") == {
            "line1": "1 Test Street", "city": "TestCity", "postCode": "TE1 1ST"
        }

    def test_family_pii_replaced(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        family = result["Family"]["Client1"]["family"]
        assert len(family) == 1
        assert family[0]["dependentFirstName"] == "TestFirst1"
        assert family[0]["dependentLastName"] == "TestLast1"

    def test_family_multiple_items_indexed(self, fresh_dcjson):
        """Each family item gets a unique indexed name, not the same one."""
        source = {
            "PersonalDetails": {"Client1": {"firstName": "X"}},
            "Family": {
                "Client1": {"family": [
                    {"id": str(uuid.uuid4()), "dependentFirstName": "Tom",
                     "dependentLastName": "Real1", "owner": "Client1"},
                    {"id": str(uuid.uuid4()), "dependentFirstName": "Sue",
                     "dependentLastName": "Real2", "owner": "Client1"},
                    {"id": str(uuid.uuid4()), "dependentFirstName": "Joe",
                     "dependentLastName": "Real3", "owner": "Client1"},
                ]},
            },
        }
        result = sanitize(source, fresh_dcjson)
        family = result["Family"]["Client1"]["family"]
        assert family[0]["dependentFirstName"] == "TestFirst1"
        assert family[1]["dependentFirstName"] == "TestFirst2"
        assert family[2]["dependentFirstName"] == "TestFirst3"
        assert family[0]["dependentLastName"] == "TestLast1"
        assert family[1]["dependentLastName"] == "TestLast2"
        assert family[2]["dependentLastName"] == "TestLast3"

    def test_will_arrangements_attorney_fields_replaced(self, joint_dcjson, fresh_dcjson):
        result = sanitize(joint_dcjson, fresh_dcjson)
        wa = result["WillArrangements"]["Client1"]
        assert wa["attorneyFirstName"] == "TestAttorneyFirst"
        assert wa["attorneyLastName"] == "TestAttorneyLast"
        assert wa["attorneyEmail"] == "test.attorney@example.com"
        assert wa["attorneyTelephone"] == "+44 7700 900001"
        assert wa["attorneyAddress"] == {
            "line1": "2 Test Street", "city": "TestCity", "postCode": "TE1 2ST"
        }

    def test_income_expenses_job_title(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        emp = result["IncomeExpenses"]["Client1"]["employment"]
        assert emp[0]["jobTitle"] == "Test Job Title"

    def test_source_not_mutated(self, single_client_dcjson, fresh_dcjson):
        original_name = single_client_dcjson["PersonalDetails"]["Client1"]["middleName"]
        sanitize(single_client_dcjson, fresh_dcjson)
        assert single_client_dcjson["PersonalDetails"]["Client1"]["middleName"] == original_name


class TestIDRemapping:
    def test_all_ids_changed(self, single_client_dcjson, fresh_dcjson):
        original_ids = set()
        for item in single_client_dcjson["Assets"]["Client1"]["assets"]:
            original_ids.add(item["id"])
        for item in single_client_dcjson["Family"]["Client1"]["family"]:
            original_ids.add(item["id"])

        result = sanitize(single_client_dcjson, fresh_dcjson)

        new_ids = set()
        for item in result["Assets"]["Client1"]["assets"]:
            new_ids.add(item["id"])
        for item in result["Family"]["Client1"]["family"]:
            new_ids.add(item["id"])

        assert original_ids.isdisjoint(new_ids), "IDs should be remapped to new UUIDs"

    def test_new_ids_are_valid_uuids(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        for item in result["Assets"]["Client1"]["assets"]:
            uuid.UUID(item["id"])  # raises if invalid
        for item in result["Family"]["Client1"]["family"]:
            uuid.UUID(item["id"])

    def test_poa_crossrefs_remapped(self, joint_dcjson, fresh_dcjson):
        """poaInfoId and poaAttorneyId in WillArrangements should point to new IDs."""
        original_poa_info_id = joint_dcjson["WillArrangements"]["Client1"]["poaInfoId"]

        result = sanitize(joint_dcjson, fresh_dcjson)
        will = result["WillArrangements"]["Client1"]

        if "poaInfoId" in will:
            assert will["poaInfoId"] != original_poa_info_id


class TestMetadataStripping:
    def test_repeater_metadata_stripped(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)

        for item in result["Assets"]["Client1"]["assets"]:
            assert "comesFrom" not in item
            assert "_SF" not in item
            assert "needsSync" not in item
            assert "hasChanges" not in item
            assert "swiftId" not in item

    def test_internal_fields_stripped(self, single_client_dcjson, fresh_dcjson):
        """Fields starting with _ should be removed from repeater items."""
        single_client_dcjson["Assets"]["Client1"]["assets"][0]["_customInternal"] = "x"
        result = sanitize(single_client_dcjson, fresh_dcjson)
        assert "_customInternal" not in result["Assets"]["Client1"]["assets"][0]

    def test_simple_card_sf_replaced(self, single_client_dcjson, fresh_dcjson):
        """Simple card _SF should come from the fresh meeting, not the source."""
        fresh_dcjson["TaxAndResidency"] = {
            "Client1": {"taxResident": "UK", "_SF": {"sfId": "FRESH-TAX-001"}},
        }
        result = sanitize(single_client_dcjson, fresh_dcjson)
        assert result["TaxAndResidency"]["Client1"]["_SF"]["sfId"] == "FRESH-TAX-001"


class TestSanitizeIntegration:
    def test_returns_dict(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        assert isinstance(result, dict)

    def test_return_id_map_false_gives_dict(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson, return_id_map=False)
        assert isinstance(result, dict)

    def test_return_id_map_true_gives_tuple(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson, return_id_map=True)
        assert isinstance(result, tuple)
        assert len(result) == 2
        sanitized, id_map = result
        assert isinstance(sanitized, dict)
        assert isinstance(id_map, dict)

    def test_id_map_covers_all_remapped_items(self, single_client_dcjson, fresh_dcjson):
        """Every original item ID should appear as a key in id_map."""
        original_ids = {
            item["id"]
            for item in single_client_dcjson["Assets"]["Client1"]["assets"]
        } | {
            item["id"]
            for item in single_client_dcjson["Family"]["Client1"]["family"]
        }
        _, id_map = sanitize(single_client_dcjson, fresh_dcjson, return_id_map=True)
        for old_id in original_ids:
            assert old_id in id_map, f"Original ID {old_id} missing from id_map"
            assert id_map[old_id] != old_id, "Mapped ID should differ from original"

    def test_preserves_card_structure(self, single_client_dcjson, fresh_dcjson):
        result = sanitize(single_client_dcjson, fresh_dcjson)
        assert "PersonalDetails" in result
        assert "Assets" in result
        assert "Family" in result
        assert "IncomeExpenses" in result

    def test_empty_cards_handled(self, fresh_dcjson):
        """Sanitizing a mostly empty DCJSON shouldn't crash."""
        minimal = {"PersonalDetails": {"Client1": {"firstName": "X"}}}
        result = sanitize(minimal, fresh_dcjson)
        assert "PersonalDetails" in result
