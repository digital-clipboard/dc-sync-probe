# DC Sync Probe — Reference

Pointers to source-of-truth files in dcReact. Read these files directly to understand API contracts, data structures, and business logic. Do not rely on summaries — the source code is authoritative.

## dcReact Codebase Location

`~/Projects/DC/dcReact/`

## Authentication & Transport

| Concern | File | What to look at |
|---------|------|----------------|
| Email/password login | `app/services/signIn.js` | `POST /signin` contract, token format |
| Salesforce SSO | `app/services/SalesforceSSO.js` | OAuth flow: check auth → get URL → exchange code |
| HTTP transport | `app/services/transporter.js` | Auth headers, session expiry detection (`logOutIfNeeded`) |
| Backend URLs | `app/services/config.js` | Environment → URL mapping |

## Meeting Search & Pull

| Concern | File | What to look at |
|---------|------|----------------|
| Search query | `app/services/searchModel.js` | GraphQL query, response parsing, deduplication (`concatMeetings`) |
| Pull meeting | `app/services/curo/getData.js` | `getMeetingFromCuro` mutation, `getData` function (line ~231) |
| POA merge | `app/services/curo/getData.js` | `transformDCJSONForSnapshot` (line ~93), `mergePoAIntoWillArrangements` (line ~46) |

## Diff Engine & Change Generation

| Concern | File | What to look at |
|---------|------|----------------|
| Core diff logic | `app/services/changeSync/diffEngine.js` | `generateAllChanges()`, `diffSimpleCard()`, `diffRepeaterCard()`, `diffIncomeExpenses()`, `diffWillArrangements()` |
| Filtering | `app/services/changeSync/diffEngine.js` | `shouldFilterChange()` — which fields/changes are excluded |
| Mandatory fields | `app/services/changeSync/diffEngine.js` | `hasMandatoryFieldsFilled()` — items that fail this are silently skipped |
| Joint splitting | `app/services/changeSync/diffEngine.js` | `splitJointItem()` — income/expenditure joint items split into two |
| Change objects | `app/services/changeSync/changeGenerator.js` | `createSimpleChange()`, `createRepeaterCreateChanges()`, `createRepeaterUpdateChange()` — change object structure |
| SF object mapping | `app/services/changeSync/sObjectResolver.js` | `needsCreate()`, `getSObjectNames()`, `isJointItem()` |
| Constants | `app/services/changeSync/constants.js` | Card lists, section names, simple vs repeater cards, skip fields |

## Sync API

| Concern | File | What to look at |
|---------|------|----------------|
| Create sync | `app/services/changeSync/sync.js` | `syncCreateChanges()` mutation, variables, response parsing |
| Update sync | `app/services/changeSync/sync.js` | `syncUpdateChanges()` mutation, sequencing (creates before updates) |

## Card Schemas (PII fields)

| Card | File | PII fields to find |
|------|------|--------------------|
| PersonalDetails | `app/cards/personalDetails.js` | Names, DOB, NI number, addresses, phone, email |
| Family | `app/cards/family.js` | Dependent first/last names |
| WillArrangements | `app/cards/willArrangements.js` | Attorney names, email, phone, address |
| IncomeExpenses | `app/cards/IncomeExpenses.js` | Job title |

## Mandatory Field Validation

| Concern | File |
|---------|------|
| Validators per card | `app/helpers/schemaHelpers/index.js` |
