"""Tests for sobject_resolver.py — SF object type resolution."""

import pytest

from dc_sync_probe.sobject_resolver import (
    get_sobject_names,
    is_joint_item,
    needs_create,
)
from dc_sync_probe.constants import (
    FAMILY_SOBJECTS,
    SF_ASSETS_AND_LIABILITIES,
    SF_FINANCIAL_ACCOUNT,
    SF_FINANCIAL_ACCOUNT_ROLE,
)


class TestIsJointItem:
    def test_joint_string(self):
        assert is_joint_item({"owner": "Joint"}) is True

    def test_joint_list_two_elements(self):
        assert is_joint_item({"owner": ["Client1", "Client2"]}) is True

    def test_not_joint_single_client(self):
        assert is_joint_item({"owner": "Client1"}) is False

    def test_not_joint_single_list(self):
        assert is_joint_item({"owner": ["Client1"]}) is False

    def test_no_owner(self):
        assert is_joint_item({}) is False


class TestNeedsCreate:
    def test_no_comes_from(self):
        assert needs_create({"id": "abc"}) is True

    def test_empty_comes_from(self):
        assert needs_create({"comesFrom": ""}) is True

    def test_has_comes_from(self):
        assert needs_create({"comesFrom": "FinServ__FinancialAccount__c"}) is False


class TestGetSobjectNamesFamily:
    def test_family_always_returns_two(self):
        names = get_sobject_names("Family", "family", {"owner": "Client1"})
        assert names == list(FAMILY_SOBJECTS)
        assert len(names) == 2


class TestGetSobjectNamesPOA:
    def test_poa_info(self):
        names = get_sobject_names("PowerOfAttorney", "poaInfo", {})
        assert names == ["Account"]

    def test_poa_attorney(self):
        names = get_sobject_names("PowerOfAttorney", "poa", {})
        assert names == list(FAMILY_SOBJECTS)


class TestGetSobjectNamesAssets:
    def test_financial_asset_single(self):
        item = {"category": "ISAs", "owner": "Client1"}
        names = get_sobject_names("Assets", "assets", item)
        assert names == [SF_FINANCIAL_ACCOUNT]

    def test_financial_asset_joint(self):
        item = {"category": "ISAs", "owner": "Joint"}
        names = get_sobject_names("Assets", "assets", item)
        assert names == [SF_FINANCIAL_ACCOUNT, SF_FINANCIAL_ACCOUNT_ROLE]

    def test_bank_asset(self):
        item = {"category": "Cash", "owner": "Client1"}
        names = get_sobject_names("Assets", "assets", item)
        assert names == [SF_FINANCIAL_ACCOUNT]

    def test_property_asset(self):
        item = {"category": "Personal Assets", "owner": "Client1",
                "comesFrom": SF_ASSETS_AND_LIABILITIES, "needsSync": True}
        names = get_sobject_names("Assets", "assets", item)
        assert names == [SF_ASSETS_AND_LIABILITIES]

    def test_other_assets_without_sync_markers(self):
        """Other Assets without sync markers → financial (investment)."""
        item = {"category": "Other Assets", "owner": "Client1"}
        names = get_sobject_names("Assets", "assets", item)
        assert names == [SF_FINANCIAL_ACCOUNT]

    def test_other_assets_with_sync_markers(self):
        """Other Assets with needsSync → plain asset."""
        item = {"category": "Other Assets", "owner": "Client1", "needsSync": True}
        names = get_sobject_names("Assets", "assets", item)
        assert names == [SF_ASSETS_AND_LIABILITIES]


class TestGetSobjectNamesLiabilities:
    def test_mortgage_single(self):
        item = {"liabilityType": "Mortgage", "owner": "Client1"}
        names = get_sobject_names("Liabilities", "liabilities", item)
        assert names == [SF_FINANCIAL_ACCOUNT]

    def test_mortgage_joint(self):
        item = {"liabilityType": "Mortgage", "owner": "Joint"}
        names = get_sobject_names("Liabilities", "liabilities", item)
        assert names == [SF_FINANCIAL_ACCOUNT, SF_FINANCIAL_ACCOUNT_ROLE]

    def test_personal_debt(self):
        item = {"liabilityType": "Personal Debt/Liability", "owner": "Client1"}
        names = get_sobject_names("Liabilities", "liabilities", item)
        assert names == [SF_ASSETS_AND_LIABILITIES]

    def test_student_loan(self):
        item = {"liabilityType": "Student Loan", "owner": "Client1"}
        names = get_sobject_names("Liabilities", "liabilities", item)
        assert names == [SF_ASSETS_AND_LIABILITIES]


class TestGetSobjectNamesPensionsProtections:
    def test_pension_single(self):
        item = {"pensionType": "DC", "owner": "Client1"}
        names = get_sobject_names("Pensions", "pensions", item)
        assert names == [SF_FINANCIAL_ACCOUNT]

    def test_pension_joint(self):
        item = {"pensionType": "DC", "owner": "Joint"}
        names = get_sobject_names("Pensions", "pensions", item)
        assert names == [SF_FINANCIAL_ACCOUNT, SF_FINANCIAL_ACCOUNT_ROLE]

    def test_protection_single(self):
        item = {"protectionType": "Life", "owner": "Client2"}
        names = get_sobject_names("Protections", "protections", item)
        assert names == [SF_FINANCIAL_ACCOUNT]


class TestGetSobjectNamesIncomeExpenses:
    def test_income(self):
        names = get_sobject_names("IncomeExpenses", "income", {})
        assert names == ["Income__c"]

    def test_expenditure(self):
        names = get_sobject_names("IncomeExpenses", "expenditure", {})
        assert names == ["Expenditure__c"]

    def test_emergency_funding(self):
        names = get_sobject_names("IncomeExpenses", "emergencyFunding", {})
        assert names == ["Emergency_Funds_Available__c"]

    def test_employment(self):
        names = get_sobject_names("IncomeExpenses", "employment", {})
        assert names == ["Account"]

    def test_unknown_section(self):
        names = get_sobject_names("IncomeExpenses", "unknown", {})
        assert names == []


class TestGetSobjectNamesUnknownCard:
    def test_returns_empty(self):
        names = get_sobject_names("UnknownCard", "section", {})
        assert names == []
