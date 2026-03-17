"""Tests for change_remapper — ID remapping in production change objects."""

from dc_sync_probe.change_remapper import (
    build_fingerprint_id_map,
    remap_change_with_id_map,
    remap_changes_with_id_map,
)


class TestRemapChangeWithIdMap:
    def test_remaps_dcid_and_formdata_id(self):
        change = {
            "dcId": "old-uuid",
            "meetingId": "prod-meeting",
            "formData": {"id": "old-uuid", "category": "ISAs"},
            "path": ["Assets", "Client1", "assets", "old-uuid", "category"],
            "slag": "Assets-Client1-assets-old-uuid-category",
        }
        id_map = {"old-uuid": "new-uuid"}
        result = remap_change_with_id_map(change, id_map, "staging-meeting")

        assert result["meetingId"] == "staging-meeting"
        assert result["dcId"] == "new-uuid"
        assert result["formData"]["id"] == "new-uuid"
        assert result["path"][3] == "new-uuid"
        assert "new-uuid" in result["slag"]
        assert "old-uuid" not in result["slag"]

    def test_unmapped_id_keeps_meeting_id_only(self):
        change = {
            "dcId": "unknown-uuid",
            "meetingId": "prod-meeting",
            "path": ["Assets", "Client1", "assets"],
        }
        id_map = {"other-uuid": "mapped-uuid"}
        result = remap_change_with_id_map(change, id_map, "staging-meeting")

        assert result["meetingId"] == "staging-meeting"
        assert result["dcId"] == "unknown-uuid"

    def test_does_not_mutate_original(self):
        change = {
            "dcId": "old-uuid",
            "meetingId": "prod",
            "formData": {"id": "old-uuid"},
            "path": ["Assets", "Client1", "assets", "old-uuid", "field"],
            "slag": "test",
        }
        id_map = {"old-uuid": "new-uuid"}
        remap_change_with_id_map(change, id_map, "staging")
        assert change["dcId"] == "old-uuid"
        assert change["meetingId"] == "prod"


class TestRemapChangesWithIdMap:
    def test_remaps_all(self):
        changes = [
            {"dcId": "a", "meetingId": "x", "path": [], "slag": ""},
            {"dcId": "b", "meetingId": "x", "path": [], "slag": ""},
        ]
        id_map = {"a": "A", "b": "B"}
        result = remap_changes_with_id_map(changes, id_map, "new-meeting")
        assert result[0]["dcId"] == "A"
        assert result[1]["dcId"] == "B"
        assert all(r["meetingId"] == "new-meeting" for r in result)


class TestBuildFingerprintIdMap:
    def test_matches_by_fingerprint(self):
        source = {
            "Assets": {
                "Client1": {
                    "assets": [
                        {"id": "src-1", "category": "ISAs", "owner": "Client1", "status": "Active"},
                    ]
                }
            }
        }
        target = {
            "Assets": {
                "Client1": {
                    "assets": [
                        {"id": "tgt-1", "category": "ISAs", "owner": "Client1", "status": "Active"},
                    ]
                }
            }
        }
        id_map = build_fingerprint_id_map(source, target)
        assert id_map == {"src-1": "tgt-1"}

    def test_no_match_when_data_differs(self):
        source = {
            "Assets": {
                "Client1": {
                    "assets": [
                        {"id": "src-1", "category": "ISAs", "owner": "Client1"},
                    ]
                }
            }
        }
        target = {
            "Assets": {
                "Client1": {
                    "assets": [
                        {"id": "tgt-1", "category": "Savings", "owner": "Client1"},
                    ]
                }
            }
        }
        id_map = build_fingerprint_id_map(source, target)
        assert id_map == {}

    def test_matches_income_expenses(self):
        source = {
            "IncomeExpenses": {
                "Client1": {
                    "income": [
                        {"id": "src-inc", "amount": 5000, "owner": "Client1"},
                    ]
                }
            }
        }
        target = {
            "IncomeExpenses": {
                "Client1": {
                    "income": [
                        {"id": "tgt-inc", "amount": 5000, "owner": "Client1"},
                    ]
                }
            }
        }
        id_map = build_fingerprint_id_map(source, target)
        assert id_map == {"src-inc": "tgt-inc"}

    def test_empty_dcjsons(self):
        assert build_fingerprint_id_map({}, {}) == {}
