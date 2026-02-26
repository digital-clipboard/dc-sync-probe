"""Tests for mandatory.py — mandatory field validators per card type."""

import pytest

from dc_sync_probe.mandatory import has_mandatory_fields_filled


class TestFamilyMandatory:
    def test_valid(self):
        item = {"relationship": "Son", "dependentLastName": "Noble"}
        assert has_mandatory_fields_filled(item, "Family", False) is True

    def test_missing_relationship(self):
        item = {"dependentLastName": "Noble"}
        assert has_mandatory_fields_filled(item, "Family", False) is False

    def test_missing_last_name(self):
        item = {"relationship": "Son"}
        assert has_mandatory_fields_filled(item, "Family", False) is False

    def test_empty_values(self):
        item = {"relationship": "", "dependentLastName": ""}
        assert has_mandatory_fields_filled(item, "Family", False) is False


class TestAssetsMandatory:
    def test_valid_financial(self):
        item = {
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "Vanguard",
            "status": "Active",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Assets", True) is True

    def test_missing_provider_financial(self):
        item = {
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "status": "Active",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Assets", True) is False

    def test_surrendered_without_date(self):
        """Surrendered is an inactive status — dateClosed required."""
        item = {
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "Vanguard",
            "status": "Surrendered",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Assets", True) is False

    def test_surrendered_with_date(self):
        item = {
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "Vanguard",
            "status": "Surrendered",
            "dateClosed": "2024-01-01",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Assets", True) is True

    def test_non_financial_asset(self):
        """Personal Assets (non-financial) don't need provider/status."""
        item = {
            "category": "Personal Assets",
            "typeOfAssetInvestment": "Property",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Assets", True) is True

    def test_two_client_no_owner(self):
        item = {
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "V",
            "status": "Active",
        }
        assert has_mandatory_fields_filled(item, "Assets", True) is False

    def test_single_client_no_owner_ok(self):
        item = {
            "category": "ISAs",
            "typeOfAssetInvestment": "Cash ISA",
            "provider": "V",
            "status": "Active",
        }
        assert has_mandatory_fields_filled(item, "Assets", False) is True


class TestLiabilitiesMandatory:
    def test_valid_mortgage(self):
        item = {
            "liabilityType": "Mortgage",
            "nameOfLender": "Halifax",
            "status": "Active",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Liabilities", True) is True

    def test_mortgage_missing_lender(self):
        item = {
            "liabilityType": "Mortgage",
            "status": "Active",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Liabilities", True) is False

    def test_personal_debt_valid(self):
        item = {
            "liabilityType": "Personal Debt/Liability",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Liabilities", True) is True

    def test_missing_type(self):
        item = {"owner": "Client1"}
        assert has_mandatory_fields_filled(item, "Liabilities", True) is False


class TestIncomeExpensesMandatory:
    def test_amount_above_zero(self):
        item = {"amount": {"amount": {"amountGBP": 1000}}}
        assert has_mandatory_fields_filled(item, "IncomeExpenses", False) is True

    def test_amount_zero(self):
        item = {"amount": {"amount": {"amountGBP": 0}}}
        assert has_mandatory_fields_filled(item, "IncomeExpenses", False) is False

    def test_emergency_funding_dict(self):
        item = {"amountOfEmergencyFunding": {"amountGBP": 5000}}
        assert has_mandatory_fields_filled(item, "IncomeExpenses", False) is True

    def test_emergency_funding_number(self):
        item = {"amountOfEmergencyFunding": 3000}
        assert has_mandatory_fields_filled(item, "IncomeExpenses", False) is True

    def test_employment_fields(self):
        item = {"employmentStatus": "Employed"}
        assert has_mandatory_fields_filled(item, "IncomeExpenses", False) is True

    def test_completely_empty(self):
        item = {}
        assert has_mandatory_fields_filled(item, "IncomeExpenses", False) is False


class TestPensionsMandatory:
    def test_valid(self):
        item = {
            "typeOfPension": "Money Purchase",
            "typeOfPlan": "Retirement Account",
            "nameOfProvider": "SJP",
            "status": "In Force",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Pensions", True) is True

    def test_missing_type_of_pension(self):
        item = {
            "typeOfPlan": "Retirement Account",
            "nameOfProvider": "SJP",
            "status": "In Force",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Pensions", True) is False

    def test_missing_type_of_plan(self):
        item = {
            "typeOfPension": "Money Purchase",
            "nameOfProvider": "SJP",
            "status": "In Force",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Pensions", True) is False

    def test_missing_provider(self):
        item = {
            "typeOfPension": "Money Purchase",
            "typeOfPlan": "Retirement Account",
            "status": "In Force",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Pensions", True) is False

    def test_two_client_no_owner(self):
        item = {
            "typeOfPension": "Money Purchase",
            "typeOfPlan": "Retirement Account",
            "nameOfProvider": "SJP",
            "status": "In Force",
        }
        assert has_mandatory_fields_filled(item, "Pensions", True) is False

    def test_surrendered_without_date(self):
        item = {
            "typeOfPension": "Money Purchase",
            "typeOfPlan": "Retirement Account",
            "nameOfProvider": "SJP",
            "status": "Surrendered",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Pensions", True) is False


class TestProtectionsMandatory:
    def test_valid(self):
        item = {
            "protectionType": "Life Cover",
            "nameOfInsuranceCompany": "Aviva",
            "status": "In Force",
            "owner": "Client1",
        }
        assert has_mandatory_fields_filled(item, "Protections", True) is True

    def test_missing_type(self):
        item = {"nameOfInsuranceCompany": "Aviva", "status": "In Force", "owner": "Client1"}
        assert has_mandatory_fields_filled(item, "Protections", True) is False

    def test_missing_company(self):
        item = {"protectionType": "Life Cover", "status": "In Force", "owner": "Client1"}
        assert has_mandatory_fields_filled(item, "Protections", True) is False

    def test_missing_status(self):
        item = {"protectionType": "Life Cover", "nameOfInsuranceCompany": "Aviva", "owner": "Client1"}
        assert has_mandatory_fields_filled(item, "Protections", True) is False


class TestUnknownCard:
    def test_unknown_card_always_passes(self):
        assert has_mandatory_fields_filled({}, "UnknownCard", False) is True
