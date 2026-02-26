"""Tests for meeting.py — Phase 1: search, pull, POA merge."""

import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from dc_sync_probe.config import Session
from dc_sync_probe.meeting import (
    _merge_poa_into_will,
    pull_meeting,
    search_meetings,
    transform_dcjson,
)


def _make_session():
    s = Session("dev")
    s.token = "test-token"
    return s


class TestSearchMeetings:
    @patch("dc_sync_probe.meeting.graphql")
    def test_deduplicates_by_swift_id(self, mock_gql):
        meetings = [
            {"contact1IdSwiftId": "sw1", "contact1IdFullName": "Ann Noble"},
            {"contact1IdSwiftId": "sw1", "contact1IdFullName": "Ann Noble (dup)"},
            {"contact1IdSwiftId": "sw2", "contact1IdFullName": "David Noble"},
        ]
        mock_gql.return_value = {"search": {"data": json.dumps(meetings)}}

        result = search_meetings(_make_session(), "Noble")
        assert len(result) == 2
        names = [m["contact1IdFullName"] for m in result]
        assert "Ann Noble" in names
        assert "David Noble" in names

    @patch("dc_sync_probe.meeting.graphql")
    def test_empty_results(self, mock_gql):
        mock_gql.return_value = {"search": {"data": "[]"}}
        result = search_meetings(_make_session(), "Nobody")
        assert result == []

    @patch("dc_sync_probe.meeting.graphql")
    def test_handles_dict_data(self, mock_gql):
        """Data may come as a list (already parsed) rather than JSON string."""
        meetings = [{"contact1IdSwiftId": "sw1", "contact1IdFullName": "Ann"}]
        mock_gql.return_value = {"search": {"data": meetings}}
        result = search_meetings(_make_session(), "Ann")
        assert len(result) == 1


class TestPullMeeting:
    @patch("dc_sync_probe.meeting.graphql")
    def test_successful_pull(self, mock_gql):
        dcjson = {"PersonalDetails": {"Client1": {"firstName": "Ann"}}}
        mock_gql.return_value = {
            "getMeetingFromCuro": {
                "success": True,
                "message": "OK",
                "DCJSON": json.dumps(dcjson),
                "client1Id": "c1",
                "client2Id": "c2",
                "meetingId": "m1",
                "sfAccountId": "sf1",
                "sfAccountId2": "sf2",
            },
        }
        result = pull_meeting(_make_session(), "swift1", "swift2", "m1")
        assert result["DCJSON"]["PersonalDetails"]["Client1"]["firstName"] == "Ann"
        assert result["meetingId"] == "m1"

    @patch("dc_sync_probe.meeting.graphql")
    def test_failed_pull_raises(self, mock_gql):
        mock_gql.return_value = {
            "getMeetingFromCuro": {
                "success": False,
                "message": "Not found",
                "DCJSON": "{}",
            },
        }
        with pytest.raises(RuntimeError, match="getMeetingFromCuro failed"):
            pull_meeting(_make_session(), "sw1")

    @patch("dc_sync_probe.meeting.graphql")
    def test_dcjson_already_dict(self, mock_gql):
        """DCJSON may come as a dict (not stringified)."""
        dcjson = {"PersonalDetails": {"Client1": {"firstName": "Ann"}}}
        mock_gql.return_value = {
            "getMeetingFromCuro": {
                "success": True,
                "DCJSON": dcjson,
                "meetingId": "m1",
            },
        }
        result = pull_meeting(_make_session(), "sw1")
        assert result["DCJSON"] == dcjson


class TestMergePOAIntoWill:
    def test_merges_poa_info(self):
        will_data = {"hasWill": True}
        poa_data = {
            "poaInfo": [{
                "id": "poa-info-1",
                "powerOfAttoneyType": "Lasting",
                "powerOfAttoneyInvoked": "No",
                "powerOfAttoneyInvokedDate": "",
                "owner": "Client1",
                "_SF": {"sfId": "poa-sf-1"},
            }],
            "poa": [],
        }
        result = _merge_poa_into_will(will_data, poa_data, "Client1")
        assert result["powerOfAttoneyType"] == "Lasting"
        assert result["poaInfoId"] == "poa-info-1"
        assert result["poaInfo_SF"] == {"sfId": "poa-sf-1"}
        assert result["hasWill"] is True

    def test_merges_poa_attorney(self):
        will_data = {"hasWill": True}
        poa_data = {
            "poaInfo": [],
            "poa": [{
                "id": "att-1",
                "attorneyFirstName": "Jane",
                "attorneyLastName": "Smith",
                "attorneyEmail": "jane@example.com",
                "attorneyTelephone": "+44 123",
                "attorneyAddress": {"line1": "5 St"},
                "swiftId": "sw-att",
                "owner": "Client1",
                "comesFrom": "ContactAccount",
                "_SF": {"sfId": "att-sf-1"},
            }],
        }
        result = _merge_poa_into_will(will_data, poa_data, "Client1")
        assert result["attorneyFirstName"] == "Jane"
        assert result["poaAttorneyId"] == "att-1"
        assert result["alreadySynced"] is True
        assert result["poaAttorney_SF"] == {"sfId": "att-sf-1"}

    def test_no_poa_data(self):
        will_data = {"hasWill": True}
        result = _merge_poa_into_will(will_data, None, "Client1")
        assert result == will_data

    def test_wrong_owner_not_merged(self):
        will_data = {"hasWill": True}
        poa_data = {
            "poaInfo": [{"owner": "Client2", "powerOfAttoneyType": "General", "id": "x"}],
            "poa": [],
        }
        result = _merge_poa_into_will(will_data, poa_data, "Client1")
        assert "powerOfAttoneyType" not in result


class TestTransformDcjson:
    def test_applies_poa_merge(self):
        dcjson = {
            "WillArrangements": {
                "Client1": {"hasWill": True},
            },
            "PowerOfAttorney": {
                "Client1": {
                    "poaInfo": [{
                        "id": "info-1",
                        "powerOfAttoneyType": "Lasting",
                        "powerOfAttoneyInvoked": "No",
                        "powerOfAttoneyInvokedDate": "",
                        "owner": "Client1",
                        "_SF": {"sfId": "sf-poa"},
                    }],
                    "poa": [],
                },
            },
        }
        result = transform_dcjson(dcjson)
        assert result["WillArrangements"]["Client1"]["powerOfAttoneyType"] == "Lasting"

    def test_does_not_mutate_input(self):
        dcjson = {
            "WillArrangements": {"Client1": {"hasWill": True}},
            "PowerOfAttorney": {
                "Client1": {
                    "poaInfo": [{"id": "x", "powerOfAttoneyType": "G", "owner": "Client1"}],
                    "poa": [],
                },
            },
        }
        original = deepcopy(dcjson)
        transform_dcjson(dcjson)
        assert dcjson == original

    def test_no_poa(self):
        dcjson = {"WillArrangements": {"Client1": {"hasWill": True}}}
        result = transform_dcjson(dcjson)
        assert result["WillArrangements"]["Client1"]["hasWill"] is True
