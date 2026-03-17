"""Tests for sync.py — Phase 4: sync mutations."""

import json
from unittest.mock import patch

import pytest

from dc_sync_probe.config import Session
from dc_sync_probe.sync import sync_create_changes, sync_update_changes
from dc_sync_probe.transport import TransportError

MEETING_ID = "test-meeting-id"


def _make_session():
    s = Session("dev")
    s.token = "test-token"
    return s


class TestSyncCreateChanges:
    @patch("dc_sync_probe.sync.graphql")
    def test_no_changes_returns_success(self, mock_gql):
        result = sync_create_changes(_make_session(), MEETING_ID, [], {}, {})
        assert result["success"] is True
        assert result["message"] == "No changes"
        mock_gql.assert_not_called()

    @patch("dc_sync_probe.sync.graphql")
    def test_successful_sync(self, mock_gql):
        mock_gql.return_value = {
            "syncCreateChanges": {
                "success": True,
                "message": "Created 2 records",
                "results": json.dumps({"dc-1": {"success": True, "_SF": {"sfId": "sf-1"}}}),
            },
        }
        changes = [{"op": "create", "dcId": "dc-1"}]
        result = sync_create_changes(_make_session(), MEETING_ID, changes, {}, {})

        assert result["success"] is True
        assert result["message"] == "Created 2 records"
        assert result["results"]["dc-1"]["success"] is True

    @patch("dc_sync_probe.sync.graphql")
    def test_failed_sync(self, mock_gql):
        mock_gql.return_value = {
            "syncCreateChanges": {
                "success": False,
                "message": "Validation failed",
                "results": "{}",
            },
        }
        result = sync_create_changes(_make_session(), MEETING_ID, [{"op": "create"}], {}, {})
        assert result["success"] is False

    @patch("dc_sync_probe.sync.graphql")
    def test_transport_error_propagates(self, mock_gql):
        mock_gql.side_effect = TransportError("network down")
        with pytest.raises(TransportError, match="network down"):
            sync_create_changes(_make_session(), MEETING_ID, [{"op": "create"}], {}, {})

    @patch("dc_sync_probe.sync.graphql")
    def test_empty_response(self, mock_gql):
        mock_gql.return_value = {}
        result = sync_create_changes(_make_session(), MEETING_ID, [{"op": "create"}], {}, {})
        assert result["success"] is False

    @patch("dc_sync_probe.sync.graphql")
    def test_results_as_dict(self, mock_gql):
        """Results may already be a dict (not stringified)."""
        mock_gql.return_value = {
            "syncCreateChanges": {
                "success": True,
                "message": "ok",
                "results": {"dc-1": {"success": True}},
            },
        }
        result = sync_create_changes(_make_session(), MEETING_ID, [{"op": "create"}], {}, {})
        assert result["results"]["dc-1"]["success"] is True

    @patch("dc_sync_probe.sync.graphql")
    def test_item_failures_detected(self, mock_gql):
        """Backend reports success but individual items failed."""
        mock_gql.return_value = {
            "syncCreateChanges": {
                "success": True,
                "message": "DONE",
                "results": json.dumps({
                    "dc-1": {"success": True, "_SF": {"sfId": "sf-1"}},
                    "dc-2": {"success": False, "error": "record type missing"},
                }),
            },
        }
        result = sync_create_changes(_make_session(), MEETING_ID, [{"op": "create"}], {}, {})
        assert result["success"] is False
        assert len(result["item_failures"]) == 1
        assert result["item_failures"][0]["id"] == "dc-2"
        assert "record type missing" in result["item_failures"][0]["error"]

    @patch("dc_sync_probe.sync.graphql")
    def test_no_item_failures_when_all_succeed(self, mock_gql):
        mock_gql.return_value = {
            "syncCreateChanges": {
                "success": True,
                "message": "ok",
                "results": {"dc-1": {"success": True}},
            },
        }
        result = sync_create_changes(_make_session(), MEETING_ID, [{"op": "create"}], {}, {})
        assert result["success"] is True
        assert result["item_failures"] == []


class TestSyncUpdateChanges:
    @patch("dc_sync_probe.sync.graphql")
    def test_no_changes(self, mock_gql):
        result = sync_update_changes(_make_session(), MEETING_ID, [], {}, {})
        assert result["success"] is True
        mock_gql.assert_not_called()

    @patch("dc_sync_probe.sync.graphql")
    def test_successful_update(self, mock_gql):
        mock_gql.return_value = {
            "syncUpdateChanges": {
                "success": True,
                "message": "Updated 3 fields",
            },
        }
        result = sync_update_changes(_make_session(), MEETING_ID, [{"op": "update"}], {}, {})
        assert result["success"] is True

    @patch("dc_sync_probe.sync.graphql")
    def test_generic_exception_wrapped(self, mock_gql):
        """Non-TransportError exceptions should be wrapped."""
        mock_gql.side_effect = RuntimeError("timeout")
        with pytest.raises(TransportError, match="transport error"):
            sync_update_changes(_make_session(), MEETING_ID, [{"op": "update"}], {}, {})
