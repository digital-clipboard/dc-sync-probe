"""Card classifications, section names, SF object mappings — mirrors constants.js."""

from __future__ import annotations

# Simple cards: single instance per client, only field updates
SIMPLE_CARDS: list[str] = [
    "PersonalDetails",
    "TaxAndResidency",
    "ClientAssistance",
    "Disclosure",
    "WillArrangements",
    "Loa",
    "Health",
]

# Repeater cards: multiple instances per client, need create changes for new items
REPEATER_CARDS: list[str] = [
    "Assets",
    "Liabilities",
    "Family",
    "Pensions",
    "Protections",
]

# IncomeExpenses nested sections → SF object name
INCOME_EXPENSES_SECTIONS: dict[str, str] = {
    "income": "Income__c",
    "expenditure": "Expenditure__c",
    "emergencyFunding": "Emergency_Funds_Available__c",
    "employment": "Account",
}

# Family / POA both produce 2 SF objects per item
FAMILY_SOBJECTS: list[str] = [
    "ContactAccount",
    "FinServ__ContactContactRelation__c",
]

# SF object names
SF_FINANCIAL_ACCOUNT = "FinServ__FinancialAccount__c"
SF_FINANCIAL_ACCOUNT_ROLE = "FinServ__FinancialAccountRole__c"
SF_ASSETS_AND_LIABILITIES = "FinServ__AssetsAndLiabilities__c"

# All card types in a DCJSON
ALL_CARD_TYPES: list[str] = [
    "PersonalDetails",
    "Assets",
    "Liabilities",
    "Pensions",
    "Protections",
    "Health",
    "Disclosure",
    "Family",
    "ClientAssistance",
    "TaxAndResidency",
    "WillArrangements",
    "IncomeExpenses",
    "ClientLetters",
    "PowerOfAttorney",
]

# Repeater section names per card (lowercase keys in DCJSON)
REPEATER_SECTION_MAP: dict[str, str] = {
    "Assets": "assets",
    "Liabilities": "liabilities",
    "Family": "family",
    "Pensions": "pensions",
    "Protections": "protections",
}

# Fields to skip when diffing/comparing simple card data
# correspondenceAddress is never synced (spec: diffEngine filters it)
SKIP_SIMPLE_CARD_FIELDS = {"id", "dirty", "hasData", "notApplicable", "correspondenceAddress"}

# Fields to skip when comparing repeater items
SKIP_REPEATER_FIELDS = {
    "id",
    "comesFrom",
    "needsSync",
    "hasChanges",
    "swiftId",
    "originalObject",
    "readOnly",
}

# Fields to exclude from formData
EXCLUDE_FROM_FORM_DATA = {"dirty", "hasData", "notApplicable", "undefined"}

# POA info fields (sync as PowerOfAttorney repeater UPDATE)
POA_INFO_FIELDS = [
    "powerOfAttoneyType",
    "powerOfAttoneyInvoked",
    "powerOfAttoneyInvokedDate",
]

# Attorney fields in WillArrangements (sync as PowerOfAttorney CREATE)
POA_ATTORNEY_FIELDS = [
    "attorneyFirstName",
    "attorneyLastName",
    "attorneyEmail",
    "attorneyTelephone",
    "attorneyAddress",
    "swiftId",
    "deleteRelation",
    "alreadySynced",
]

# Internal POA tracking fields merged from PowerOfAttorney
POA_INTERNAL_FIELDS = [
    "poaInfoId",
    "poaInfo_SF",
    "poaAttorneyId",
    "poaAttorney_SF",
]

ALL_POA_FIELDS = set(POA_INFO_FIELDS + POA_ATTORNEY_FIELDS + POA_INTERNAL_FIELDS)

# Investment asset categories (from assetsHelper)
INVESTMENT_CATEGORIES = {
    "Insurance Bonds",
    "ISAs",
    "Collective investments",
    "Annuity",
    "Savings",
    "Unknown Category",
    "Investment",
    "Other Assets",
}

# Asset categories that are plain assets (not investments) when they have sync markers
ASSET_CATEGORIES = {"Stocks & Shares", "Personal Assets", "Other Assets"}

BANK_CATEGORIES = {"Cash"}

# Liability categories that are non-mortgage
LIABILITY_CATEGORIES = {
    "Hire Purchase",
    "Personal Debt/Liability",
    "Student Loan",
    "Tax Liability",
    "Other",
}
