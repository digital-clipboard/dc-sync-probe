"""Tests for change_sanitizer — sanitize raw production change objects."""

from dc_sync_probe.change_sanitizer import sanitize_change, sanitize_changes


class TestSanitizeChange:
    def test_strips_is_automated_from_formdata(self):
        change = {
            "op": "update",
            "formData": {"id": "abc", "isAutomated": True, "category": "ISAs"},
        }
        result = sanitize_change(change)
        assert "isAutomated" not in result["formData"]
        assert result["formData"]["category"] == "ISAs"

    def test_replaces_pii_in_formdata(self):
        change = {
            "op": "update",
            "formData": {
                "dependentFirstName": "RealFirst",
                "dependentLastName": "RealLast",
                "category": "ISAs",
            },
        }
        result = sanitize_change(change)
        assert result["formData"]["dependentFirstName"] == "TestFirst"
        assert result["formData"]["dependentLastName"] == "TestLast"
        assert result["formData"]["category"] == "ISAs"

    def test_replaces_attorney_pii(self):
        change = {
            "op": "create",
            "formData": {
                "attorneyFirstName": "Real",
                "attorneyLastName": "Attorney",
                "attorneyEmail": "real@email.com",
            },
        }
        result = sanitize_change(change)
        assert result["formData"]["attorneyFirstName"] == "TestAttorneyFirst"
        assert result["formData"]["attorneyLastName"] == "TestAttorneyLast"
        assert result["formData"]["attorneyEmail"] == "test.attorney@example.com"

    def test_no_formdata_returns_unchanged(self):
        change = {"op": "update", "path": ["Assets", "Client1", "assets"]}
        result = sanitize_change(change)
        assert result == change

    def test_does_not_mutate_original(self):
        change = {
            "op": "update",
            "formData": {"isAutomated": True, "category": "ISAs"},
        }
        sanitize_change(change)
        assert change["formData"]["isAutomated"] is True


class TestSanitizeChanges:
    def test_sanitizes_all_changes(self):
        changes = [
            {"op": "update", "formData": {"isAutomated": True}},
            {"op": "create", "formData": {"dependentFirstName": "Real"}},
        ]
        result = sanitize_changes(changes)
        assert len(result) == 2
        assert "isAutomated" not in result[0]["formData"]
        assert result[1]["formData"]["dependentFirstName"] == "TestFirst"

    def test_empty_list(self):
        assert sanitize_changes([]) == []
