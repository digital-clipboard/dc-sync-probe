"""Tests for verify.py — Phase 5 verification logic."""

from copy import deepcopy

import pytest

from dc_sync_probe.verify import _deep_equal, _item_fingerprint, verify


class TestVerifyDeepEqual:
    def test_equal_dicts(self):
        assert _deep_equal({"a": 1}, {"a": 1}) is True

    def test_int_float_comparison(self):
        assert _deep_equal(1, 1.0) is True

    def test_nested(self):
        assert _deep_equal({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]}) is True

    def test_not_equal(self):
        assert _deep_equal({"a": 1}, {"a": 2}) is False


class TestItemFingerprint:
    def test_ignores_internal_fields(self):
        fp1 = _item_fingerprint({"name": "a", "_SF": {"x": 1}})
        fp2 = _item_fingerprint({"name": "a"})
        assert fp1 == fp2

    def test_ignores_skip_fields(self):
        fp1 = _item_fingerprint({"name": "a", "comesFrom": "X", "needsSync": True})
        fp2 = _item_fingerprint({"name": "a"})
        assert fp1 == fp2

    def test_different_values_different_fingerprint(self):
        fp1 = _item_fingerprint({"name": "a"})
        fp2 = _item_fingerprint({"name": "b"})
        assert fp1 != fp2


class TestVerifySimpleCards:
    def test_matching_simple_card(self):
        expected = {"Health": {"Client1": {"inGoodHealth": True}}}
        actual = {"Health": {"Client1": {"inGoodHealth": True}}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 0
        assert len(report["matched"]) >= 1

    def test_mismatched_simple_card(self):
        expected = {"Health": {"Client1": {"inGoodHealth": True}}}
        actual = {"Health": {"Client1": {"inGoodHealth": False}}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 1
        assert report["mismatches"][0]["path"] == "Health.Client1.inGoodHealth"

    def test_skips_pii_fields(self):
        """PII fields should be skipped, not compared."""
        expected = {
            "PersonalDetails": {
                "Client1": {"middleName": "TestMiddle", "dateOfBirth": "1990-01-01"},
            },
        }
        actual = {
            "PersonalDetails": {
                "Client1": {"middleName": "RealMiddle", "dateOfBirth": "1985-06-15"},
            },
        }
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 0
        assert len(report["skipped"]) >= 2

    def test_skips_internal_fields(self):
        expected = {"Health": {"Client1": {"_SF": {"sfId": "a"}, "inGoodHealth": True}}}
        actual = {"Health": {"Client1": {"_SF": {"sfId": "b"}, "inGoodHealth": True}}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 0

    def test_missing_client_section(self):
        expected = {"Health": {"Client1": {"inGoodHealth": True}}}
        actual = {"Health": {}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 1
        assert "Missing entire client section" in report["mismatches"][0]["issue"]


class TestVerifyRepeaterCards:
    def test_matching_repeater(self):
        item = {"category": "ISAs", "value": 50000, "owner": "Client1"}
        expected = {"Assets": {"Client1": {"assets": [item]}}}
        actual = {"Assets": {"Client1": {"assets": [deepcopy(item)]}}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 0

    def test_mismatched_repeater_field(self):
        """Items that match by fingerprint but differ in a field produce a mismatch.

        The fingerprint uses all non-internal/non-skip fields, so if two items
        don't match on any field the fingerprint won't match at all.
        We test the "no matching item" mismatch path instead.
        """
        orig = {"category": "ISAs", "value": 50000, "owner": "Client1"}
        changed = {"category": "ISAs", "value": 55000, "owner": "Client1"}
        expected = {"Assets": {"Client1": {"assets": [orig]}}}
        actual = {"Assets": {"Client1": {"assets": [changed]}}}
        report = verify(expected, actual)
        # Items differ in value so fingerprints won't match → "No matching item"
        assert len(report["mismatches"]) >= 1

    def test_item_count_mismatch(self):
        item = {"category": "ISAs", "value": 50000, "owner": "Client1"}
        expected = {"Assets": {"Client1": {"assets": [item]}}}
        actual = {"Assets": {"Client1": {"assets": []}}}
        report = verify(expected, actual)
        count_mismatches = [m for m in report["mismatches"] if "count" in m.get("issue", "").lower()]
        assert len(count_mismatches) >= 1


class TestVerifyNotes:
    def test_matching_notes(self):
        expected = {"Notes": {"Client1": {"notes": "Hello"}}}
        actual = {"Notes": {"Client1": {"notes": "Hello"}}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 0

    def test_changed_notes(self):
        expected = {"Notes": {"Client1": {"notes": "old"}}}
        actual = {"Notes": {"Client1": {"notes": "new"}}}
        report = verify(expected, actual)
        assert len(report["mismatches"]) == 1


class TestVerifyIncomeExpenses:
    def test_matching_income(self):
        item = {"category": "Employment", "amount": 50000, "owner": "Client1"}
        expected = {"IncomeExpenses": {"Client1": {"income": [item]}}}
        actual = {"IncomeExpenses": {"Client1": {"income": [deepcopy(item)]}}}
        report = verify(expected, actual)
        ie_mismatches = [m for m in report["mismatches"] if "IncomeExpenses" in m.get("path", "")]
        assert len(ie_mismatches) == 0


class TestVerifyIntegration:
    def test_full_report_structure(self, single_client_dcjson):
        report = verify(single_client_dcjson, deepcopy(single_client_dcjson))
        assert "matched" in report
        assert "mismatches" in report
        assert "skipped" in report
        assert isinstance(report["matched"], list)
        assert isinstance(report["mismatches"], list)
        assert isinstance(report["skipped"], list)

    def test_empty_dcjsons(self):
        report = verify({}, {})
        assert report["matched"] == []
        assert report["mismatches"] == []
        assert report["skipped"] == []
