# Sync Test Tool — Requirements Specification

## Context

We need a **standalone Python CLI tool** (separate project) that tests the DC sync pipeline end-to-end. It takes a real DCJSON snapshot, sanitizes personal information, replicates the data into a fresh Salesforce meeting, and verifies the result. The dcReact codebase is the reference for all business logic, data structures, and API contracts documented here.

**Scope**: Single-client and joint meetings. Fully CLI — no UI.

---

## High-Level Flow

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  PHASE 1         │     │  PHASE 2         │     │  PHASE 3         │     │  PHASE 4         │     │  PHASE 5         │
│  Find & Pull     │────>│  Sanitize DCJSON │────>│  Generate Changes│────>│  Sync Changes    │────>│  Verify          │
│  Meeting         │     │                  │     │                  │     │                  │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘

 Search by name       Strip PII, remap IDs   Diff engine produces     CREATE then UPDATE      Re-pull & compare
 Pick from results    strip sync metadata     CREATE + UPDATE changes  via GraphQL mutations   field-by-field
 Pull DCJSON
```

---

## Authentication & Backend Access

### How Auth Works in dcReact (reference)

The app authenticates via two methods:

**1. Email/Password Login**
- `POST {apiUrl}/signin` with body `{ email, password }`
- Returns `{ user: {...}, token: "jwt-string" }`
- Token stored and sent as `Authorization: Bearer {token}` on all subsequent requests
- Source: `~/Projects/DC/dcReact/app/services/signIn.js`

**2. SSO (Salesforce & Microsoft)**

*Salesforce SSO flow:*
1. Check auth status: `query{ isUserAuthenticatedWithSalesforce { success, message } }`
2. Get OAuth URL: `query{ getAuthorizationUrl { success, url } }`
3. User completes OAuth in browser → gets authorization code
4. Exchange code: `mutation { authenticateSalesforceWithSSO(code: "...") { success, message } }`
- Source: `~/Projects/DC/dcReact/app/services/SalesforceSSO.js`, `~/Projects/DC/dcReact/ios/SSO/SfSSOModel.m`


### Session Management
- 401 responses or messages containing "invalid signature", "you must be authenticated", "token_session_timeout", "jwtautherror" → session expired, must re-authenticate
- Source: `~/Projects/DC/dcReact/app/services/transporter.js` (logOutIfNeeded function)

### Backend Environments
| Environment | API URL | GraphQL URL |
|-------------|---------|-------------|
| Local | `http://localhost:3000` | `http://localhost:3000/graphql` |
| Dev | `https://backend.dev.sjp.digitalclipboard.com` | `.../graphql` |
| Staging/UAT | `https://backend.uat.sjp.digitalclipboard.com` | `.../graphql` |
| DC Prod | `https://backend.digitalclipboard.com` | `.../graphql` |
| SJP UAT | `https://nlb-dcservicesuat.sjp.co.uk` | `.../graphql` |
| SJP Prod | `https://nlb-dcservices.sjp.co.uk` | `.../graphql` |

Source: `~/Projects/DC/dcReact/app/services/config.js`

### All requests use
- `Content-Type: application/json`
- `Authorization: Bearer {token}`
- POST method for all GraphQL calls

---

## Phase 1: Find & Pull Meeting

### Step 1a: Search for a Meeting

The CLI should let the user search by client name and pick a meeting from the results. This also enables joint meeting detection automatically.

**GraphQL Query:**
```graphql
query {
  search(query: "<search_term>") {
    data
  }
}
```
- Timeout: default (45s)
- Requires Salesforce authentication first (see SF SSO flow above)
- Source: `~/Projects/DC/dcReact/app/services/searchModel.js`

**Response:** `data` is a JSON string containing an array of meeting objects:
```json
[
  {
    "meetingId": "uuid",
    "contact1IdFullName": "John Smith",
    "contact2IdFullName": "Jane Smith",
    "contact1IdAddress": "123 Main St...",
    "contact1IdSwiftId": "sf-account-id-1",
    "contact2IdSwiftId": "sf-account-id-2"
  }
]
```

**Joint meeting detection:** If `contact2IdSwiftId` is present and non-empty → joint meeting. Pass both swift IDs to Phase 1b.

**Deduplication:** Multiple results may share the same `contact1IdSwiftId`. Deduplicate by this field.
Source: `~/Projects/DC/dcReact/app/services/searchModel.js` (concatMeetings function)

### Step 1b: Pull the Meeting

Download the full meeting DCJSON from Salesforce.

**GraphQL Mutation:**
```graphql
mutation {
  getMeetingFromCuro(
    swift1: "<contact1IdSwiftId>",
    swift2: "<contact2IdSwiftId or empty>",
    search: "true",
    meetingId: "<meetingId>"
  ) {
    success
    message
    DCJSON
    client1Id
    client2Id
    meetingId
    sfAccountId
    sfAccountId2
  }
}
```
- Timeout: 90,000ms
- `swift2`: empty string `""` for single-client meetings
- `meetingId`: optional — if omitted, backend uses swift IDs to find the meeting
- Source: `~/Projects/DC/dcReact/app/services/curo/getData.js` (getData function, line 231)

**Response:** `DCJSON` contains the full meeting snapshot as a JSON object.

### Step 1c: Transform DCJSON (POA Merge)

After pulling, apply the POA merge transformation so the snapshot matches the format the diff engine expects. PowerOfAttorney data (always under `Client1`) must be merged into WillArrangements for both clients based on each POA item's `owner` field.

**Logic** (from `~/Projects/DC/dcReact/app/services/curo/getData.js`, `transformDCJSONForSnapshot` line 93):
1. Deep clone the DCJSON
2. Get `poaData = DCJSON.PowerOfAttorney.Client1`
3. For each client (`Client1`, `Client2`):
   - Find POA items where `owner === clientKey`
   - Merge `poaInfo` fields → `poaInfoId`, `poaInfo_SF`, POA type fields into WillArrangements
   - Merge `poa` (attorney) fields → `poaAttorneyId`, `poaAttorney_SF`, attorney contact fields into WillArrangements

Source: `~/Projects/DC/dcReact/app/services/curo/getData.js` (mergePoAIntoWillArrangements, line 46)

---

## Phase 2: Sanitize the Source DCJSON

Take the input DCJSON (the real data to replicate), remove personal information, remap IDs, and strip sync metadata.

### Step 2a: Replace Personal Information

**26 PII fields across 4 cards, with their required action:**

> **Rule: Always use synthetic test values when replacing PII. Never set them to null.** Since the source DCJSON comes from an existing SF meeting, all mandatory fields will already be populated. However, the sanitizer must not break this by nullifying fields — the diff engine silently skips items that fail `hasMandatoryFieldsFilled` (`~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js:29`). A post-sanitization validation step is recommended as a defensive check.

#### PersonalDetails — 13 fields
Source: `~/Projects/DC/dcReact/app/cards/personalDetails.js`

| Field | Display Name | Action |
|-------|-------------|--------|
| `fullName` | Full Name | EXCLUDE — never synced (filtered by diffEngine) |
| `firstName` | First Name | KEEP from fresh meeting |
| `lastName` | Last Name | KEEP from fresh meeting |
| `email1` | Work Email | KEEP from fresh meeting |
| `middleName` | Middle Name | `"TestMiddle"` |
| `nickname` | Preferred Name | `"TestNickname"` |
| `dateOfBirth` | Date of Birth | `"1990-01-01"` (or equivalent synthetic date) |
| `nationalInsuranceNumber` | National Insurance Number | `"QQ123456C"` |
| `maidenName` | Maiden Name | `"TestMaiden"` |
| `telephone1` | Mobile | `"+44 7700 900000"` |
| `email2` | Personal Email | `"test.personal@example.com"` |
| `homeAddress` | Home Address | `{ "line1": "1 Test Street", "city": "TestCity", "postCode": "TE1 1ST" }` (or appropriate synthetic address object) |
| `correspondenceAddress` | Correspondence Address | EXCLUDE — never synced (filtered by diffEngine) |

#### Family — 2 fields (per repeater item)
Source: `~/Projects/DC/dcReact/app/cards/family.js`

| Field | Display Name | Action |
|-------|-------------|--------|
| `dependentFirstName` | First Name | `"TestFirst1"`, `"TestFirst2"`, etc. (indexed per item) |
| `dependentLastName` | Last Name | `"TestLast1"`, `"TestLast2"`, etc. (indexed per item) |

#### WillArrangements (Power of Attorney attorneys) — 5 fields
Source: `~/Projects/DC/dcReact/app/cards/willArrangements.js`

| Field | Display Name | Action |
|-------|-------------|--------|
| `attorneyFirstName` | Attorney First Name | `"TestAttorneyFirst"` |
| `attorneyLastName` | Attorney Last Name | `"TestAttorneyLast"` |
| `attorneyEmail` | Attorney Email | `"test.attorney@example.com"` |
| `attorneyTelephone` | Attorney Telephone | `"+44 7700 900001"` |
| `attorneyAddress` | Attorney Address | `{ "line1": "2 Test Street", "city": "TestCity", "postCode": "TE1 2ST" }` (or appropriate synthetic address object) |

#### IncomeExpenses — 1 field (per employment item)
Source: `~/Projects/DC/dcReact/app/cards/IncomeExpenses.js`

| Field | Display Name | Action |
|-------|-------------|--------|
| `jobTitle` | Job title | `"Test Job Title"` |

#### Fields auto-excluded by the diff engine (no action needed)
These never generate sync changes regardless:
- `PersonalDetails.*.isThisYourCorrespondenceAddress`
- `*.fullName` (any card, case-insensitive)
- Source: `~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js:818-834` (`shouldFilterChange`)

### Step 2b: Remap Local IDs

There are two types of IDs to understand:

- **`item.id`** — Local/client-side UUIDs, auto-generated when an item is created in the app. The diff engine uses these to track items internally. Source DCJSON's local IDs must be remapped to new UUIDs so the changes reference valid local IDs for the target meeting.
- **`_SF.sfId`** — Salesforce record IDs. These do **not** exist until after a successful CREATE sync. The backend assigns them. To get the new SF IDs, **re-pull the meeting after syncing** and match items by their data to discover which `_SF.sfId` was assigned.

This step only remaps `item.id` (local UUIDs). SF IDs are handled naturally: we strip `_SF` in Step 2c, and after syncing (Phase 4) we re-pull the meeting (Phase 5) to get the new SF-assigned IDs.

**Where local IDs (`item.id`) exist:**

| Location | Example path |
|----------|-------------|
| Repeater items | `Assets.Client1.assets[i].id` |
| IncomeExpenses items | `IncomeExpenses.Client1.income[i].id` |
| POA info items | `PowerOfAttorney.Client1.poaInfo[i].id` |
| POA attorney items | `PowerOfAttorney.Client1.poa[i].id` |
| WillArrangements (merged refs) | `WillArrangements.Client1.poaInfoId`, `.poaAttorneyId` |

**Repeater section names** (lowercase keys in DCJSON):

| Card | Section(s) |
|------|-----------|
| Assets | `assets` |
| Liabilities | `liabilities` |
| Family | `family` |
| Pensions | `pensions` |
| Protections | `protections` |
| IncomeExpenses | `income`, `expenditure`, `emergencyFunding`, `employment` |

Source: `~/Projects/DC/dcReact/app/services/changeSync/constants.js`

**Algorithm:**
1. Walk all repeater items across all cards → build `Map<oldId, newUUID>`
2. Replace every `item.id` with its mapped new UUID
3. Replace cross-references (`poaInfoId`, `poaAttorneyId` in WillArrangements)

### Step 2c: Strip Sync Metadata

Remove SF-specific metadata so the diff engine treats every repeater item as brand new (CREATE).

**From repeater items, remove:**
| Field | Why |
|-------|-----|
| `comesFrom` | Tells diff engine item exists in SF. Removing forces CREATE. See `needsCreate()` in `~/Projects/DC/dcReact/app/services/changeSync/sObjectResolver.js:124` |
| `_SF` | SF record IDs from source meeting — invalid for target. New SF IDs are assigned by the backend on CREATE sync and discovered by re-pulling the meeting in Phase 5 |
| `needsSync` | Internal sync state |
| `hasChanges` | Internal change tracking |
| `swiftId` | SF-specific identifier |
| `originalObject` | Backup of original data |
| `readOnly` | Internal flag |
| `isAutomated` | SF-managed field. If present in formData, the backend logs "Missing Mapping" errors and the sync fails. SF sets this automatically on records — it must never be sent in CREATE/UPDATE payloads |
| Any `_*` prefixed field | Internal metadata convention |

**For simple cards:** Replace `_SF` with `_SF` from the **fresh meeting** (contains the correct SF record IDs for the target meeting).

Simple cards: `PersonalDetails`, `TaxAndResidency`, `ClientAssistance`, `Disclosure`, `WillArrangements`, `Loa`, `Health`
Source: `~/Projects/DC/dcReact/app/services/changeSync/constants.js:13-21`

**Copy top-level identifiers from fresh meeting:** After all sanitization steps, copy `id`, `Client1Id`, `Client2Id`, and `meta` from the fresh DCJSON into the sanitized DCJSON. The backend's data factories (e.g. `Account.js:getClientInfo`) use `meta.Client*.SwiftId` to resolve the correct Salesforce Account records. Without this, the sanitized DCJSON points to the source meeting's SF accounts, causing CREATE failures.

---

## Phase 3: Generate Changes

Feed the **fresh DCJSON** (as the "original" — what SF currently has) and the **sanitized DCJSON** (as the "current" — what we want) into a diff engine to produce CREATE and UPDATE changes.

### Diff Engine Logic to Reimplement

The Python tool needs to reimplement the core diff logic from `~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js`. Here's what `generateAllChanges()` does (line 844):

1. **Diff simple cards** (PersonalDetails, TaxAndResidency, ClientAssistance, Disclosure, Loa, Health) — produces UPDATE changes for each field that differs
   - Skip internal fields: `id`, `dirty`, `hasData`, `notApplicable`, `correspondenceAddress`, any `_*` prefixed
   - WillArrangements handled separately (step 2)
   - Source: `diffSimpleCard()` at ~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js

2. **Diff WillArrangements** — special attorney handling
   - Regular WillArrangements fields → UPDATE changes
   - POA attorney fields (merged from PowerOfAttorney) → CREATE changes for new POA items
   - Source: `diffWillArrangements()` at ~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js

3. **Diff repeater cards** (Assets, Liabilities, Family, Pensions, Protections)
   - Items without `comesFrom` → CREATE changes (with `formData` = full item)
   - Items with `comesFrom` that have changed fields → UPDATE changes
   - Items must pass `hasMandatoryFieldsFilled` or they're skipped
   - Skip fields when comparing repeater items: `id`, `comesFrom`, `needsSync`, `hasChanges`, `swiftId`, `originalObject`, `readOnly`, `isAutomated`
   - Iterates both Client1 and Client2
   - Source: `diffRepeaterCard()` at ~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js

4. **Diff IncomeExpenses** — nested repeaters with joint splitting
   - Same as repeater cards but per-section (income, expenditure, emergencyFunding, employment)
   - **Joint item splitting** (income/expenditure only): Items with `owner === 'Joint'` are split into 2 items, each with half the amount. Client1 keeps original ID, Client2 gets new UUID.
   - Source: `diffIncomeExpenses()`, `splitJointItem()` at ~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js:396-417

5. **Diff Notes** → UPDATE changes only
6. **Diff ClientNeeds** → UPDATE changes only
7. **Filter** via `shouldFilterChange()` — removes `isThisYourCorrespondenceAddress` and `*.fullName` changes

### Change Object Structure

```json
{
  "op": "create | update",
  "path": ["cardName", "clientNumber", "sectionName?", "itemId?", "fieldName/sObjectName"],
  "slag": "dot.notation.path",
  "dcId": "item-local-uuid",
  "type": "simple | repeater",
  "val": "<new value>",
  "oldVal": "<previous value>",
  "formData": "<complete item data (for creates)>",
  "meetingId": "meeting-uuid",
  "fieldName": "string",
  "sObjectName": "SF object name",
  "timestamp": "ISO8601",
  "joint": "boolean",
  "joinedJoint": "boolean"
}
```

Source: `~/Projects/DC/dcReact/app/services/changeSync/changeGenerator.js`

### SF Object Mappings

> **Note:** The backend determines the correct SF object based on item sub-type (e.g., investment vs other asset). The tool does not need to handle this — it just passes the change objects and the backend resolves the mapping. This table is reference context only.

| Card / Section | SF Object(s) | Joint handling |
|----------------|-------------|----------------|
| Assets | `FinServ__FinancialAccount__c` or `FinServ__AssetsAndLiabilities__c` (backend decides) | + `FinServ__FinancialAccountRole__c` for joint |
| Liabilities | `FinServ__FinancialAccount__c` or `FinServ__AssetsAndLiabilities__c` (backend decides) | + Role for joint |
| Family | `ContactAccount` + `FinServ__ContactContactRelation__c` | Joint: 2 Relations |
| Pensions | `FinServ__FinancialAccount__c` | + Role for joint |
| Protections | `FinServ__FinancialAccount__c` | + Role for joint |
| IncomeExpenses.income | `Income__c` | Joint: split into 2 items |
| IncomeExpenses.expenditure | `Expenditure__c` | Joint: split into 2 items |
| IncomeExpenses.emergencyFunding | `Emergency_Funds_Available__c` | No split |
| IncomeExpenses.employment | `Account` | No split |
| PowerOfAttorney (poaInfo) | `Account` | Per owner field |
| PowerOfAttorney (poa) | `ContactAccount` + `ContactRelation` | Per owner field |

Source: `~/Projects/DC/dcReact/app/services/changeSync/constants.js`, `~/Projects/DC/dcReact/app/services/changeSync/sObjectResolver.js`

### Joint Meeting Detection
```python
is_two_client_meeting = bool(current.get("PersonalDetails", {}).get("Client2", {}).get("firstName"))
```
Source: ~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js line 328

### Joint Item Detection
```python
is_joint = item.get("owner") == "Joint" or (isinstance(item.get("owner"), list) and len(item["owner"]) == 2)
```
Source: `~/Projects/DC/dcReact/app/services/changeSync/sObjectResolver.js:18`

---

## Phase 4: Sync Changes

### Step 4a: Send CREATE Changes

**GraphQL Mutation:**
```graphql
mutation SyncCreateChanges(
  $meetingId: UUID!,
  $changes: [ChangeProperInput!]!,
  $initialDCJSON: JSON!,
  $currentDCJSON: JSON!,
  $source: String!
) {
  syncCreateChanges(
    meetingId: $meetingId,
    changes: $changes,
    initialDCJSON: $initialDCJSON,
    currentDCJSON: $currentDCJSON,
    source: $source
  ) {
    success
    message
    results
  }
}
```

| Variable | Value |
|----------|-------|
| `meetingId` | UUID from Phase 1 |
| `changes` | Array of CREATE change objects |
| `initialDCJSON` | Fresh DCJSON (original snapshot) |
| `currentDCJSON` | Sanitized DCJSON (target state) |
| `source` | `"ios"` |

- Timeout: 600,000ms (10 minutes — real meetings with many repeater items need significantly more than the app's default 60s)
- Source: `~/Projects/DC/dcReact/app/services/changeSync/sync.js:20-101`

**Response:**
```json
{
  "success": true,
  "message": "string",
  "results": {
    "<dcId>": {
      "success": true,
      "_SF": { "sfId": "new-sf-record-id" }
    }
  }
}
```
Note: `results` may come as a JSON string that needs parsing.

### Step 4b: Send UPDATE Changes

**MUST run after CREATE completes** — update changes on repeater items reference `_SF.sfId` that only exists after creation.

**GraphQL Mutation:**
```graphql
mutation SyncUpdateChanges(
  $meetingId: UUID!,
  $changes: [ChangeProperInput!]!,
  $initialDCJSON: JSON!,
  $currentDCJSON: JSON!,
  $source: String!
) {
  syncUpdateChanges(
    meetingId: $meetingId,
    changes: $changes,
    initialDCJSON: $initialDCJSON,
    currentDCJSON: $currentDCJSON,
    source: $source
  ) {
    success
    message
  }
}
```

Same variables as Step 4a but with UPDATE change objects. Timeout: 600,000ms.

Source: `~/Projects/DC/dcReact/app/services/changeSync/sync.js:113-179`

---

## Phase 5: Verify

### Step 5a: Re-pull the Meeting
Call `getMeetingFromCuro` again (same as Phase 1b) to get the current state from SF.

### Step 5b: Compare DCJSONs

**Simple cards** — field-by-field:
- Skip: `id`, `dirty`, `hasData`, `notApplicable`, `correspondenceAddress`, `isThisYourCorrespondenceAddress`, `fullName`, `_*` prefixed, PII fields (except kept ones)
- Compare remaining fields for equality

**Repeater cards** — item matching by data fingerprint:
- IDs will differ (SF assigns new ones on pull)
- Match items by comparing non-internal, non-PII field values (excluding `id`, `comesFrom`, `needsSync`, `hasChanges`, `swiftId`, `originalObject`, `readOnly`, `isAutomated`)
- Also skip `poaInfoId` and `poaAttorneyId` — these are local UUID cross-references remapped during sanitization that don't survive the SF round-trip
- Verify item counts per section
- For each matched pair, compare all syncable fields
- On fingerprint mismatch, output both the expected fields and the actual item fingerprints to aid debugging

**Output:** structured report with matched/mismatched/skipped counts and per-field mismatch details.

---

## DCJSON Structure Reference

> **Important: Owner field pattern.** All repeater card items (Assets, Liabilities, Pensions, Protections, Family, IncomeExpenses, PowerOfAttorney) are stored under `Client1` and use an `owner` field to indicate which client they belong to (`"Client1"`, `"Client2"`, or `"Joint"`). This is not specific to PowerOfAttorney — it applies to all repeater objects.

```json
{
  "id": "meeting-uuid",
  "Client1Id": "client-1-uuid",
  "Client2Id": "client-2-uuid or null",
  "meta": { "Client1": {}, "Client2": {} },

  "PersonalDetails": {
    "Client1": { "firstName": "...", "lastName": "...", "_SF": {}, "..." : "..." },
    "Client2": { "..." : "..." }
  },
  "Assets": {
    "Client1": {
      "assets": [
        { "id": "uuid", "owner": "Client1", "comesFrom": "...", "_SF": {}, "..." : "..." },
        { "id": "uuid", "owner": "Client2", "..." : "..." },
        { "id": "uuid", "owner": "Joint", "..." : "..." }
      ]
    }
  },
  "IncomeExpenses": {
    "Client1": {
      "income": [ { "id": "...", "owner": "Client1" } ],
      "expenditure": [ { "id": "...", "owner": "Joint" } ],
      "emergencyFunding": [],
      "employment": [ { "id": "...", "owner": "Client1" } ]
    }
  },
  "PowerOfAttorney": {
    "Client1": {
      "poaInfo": [ { "id": "...", "owner": "Client1" } ],
      "poa": [ { "id": "...", "owner": "Client1" } ]
    }
  },
  "WillArrangements": { "Client1": {}, "Client2": {} },
  "Notes": { "Client1": {}, "Client2": {} },
  "ClientNeeds": { "Client1": {}, "Client2": {} }
}
```

All card types: `PersonalDetails`, `Assets`, `Liabilities`, `Pensions`, `Protections`, `Health`, `Disclosure`, `Family`, `ClientAssistance`, `TaxAndResidency`, `WillArrangements`, `IncomeExpenses`, `ClientLetters`, `PowerOfAttorney`
Source: `~/Projects/DC/dcReact/app/services/curo/getData.js:6-11`

---

## Key Source Files Reference

| File | What to look at |
|------|----------------|
| `~/Projects/DC/dcReact/app/services/changeSync/diffEngine.js` | Core diff logic — `generateAllChanges()`, `shouldFilterChange()`, `hasMandatoryFieldsFilled()`, `splitJointItem()`, `diffWillArrangements()` |
| `~/Projects/DC/dcReact/app/services/changeSync/changeGenerator.js` | Change object creation — `createSimpleChange()`, `createRepeaterCreateChanges()`, `createRepeaterUpdateChange()` |
| `~/Projects/DC/dcReact/app/services/changeSync/sObjectResolver.js` | SF object mapping — `needsCreate()`, `getSObjectNames()`, joint item detection |
| `~/Projects/DC/dcReact/app/services/changeSync/sync.js` | GraphQL sync calls — `syncCreateChanges()`, `syncUpdateChanges()` |
| `~/Projects/DC/dcReact/app/services/changeSync/constants.js` | Card lists, section names, SF object names |
| `~/Projects/DC/dcReact/app/services/curo/getData.js` | Meeting pull, DCJSON transforms, POA merge |
| `~/Projects/DC/dcReact/app/services/searchModel.js` | Client search query and result parsing |
| `~/Projects/DC/dcReact/app/services/signIn.js` | Email/password login, MS SSO exchange |
| `~/Projects/DC/dcReact/app/services/SalesforceSSO.js` | Salesforce SSO flow |
| `~/Projects/DC/dcReact/app/services/transporter.js` | HTTP transport, auth headers, session handling |
| `~/Projects/DC/dcReact/app/services/config.js` | Backend URLs per environment |
| `~/Projects/DC/dcReact/app/cards/personalDetails.js` | PII fields (13) |
| `~/Projects/DC/dcReact/app/cards/family.js` | PII fields (2) |
| `~/Projects/DC/dcReact/app/cards/willArrangements.js` | PII fields (5) + POA schema |
| `~/Projects/DC/dcReact/app/cards/IncomeExpenses.js` | PII field (1) |
| `~/Projects/DC/dcReact/app/helpers/schemaHelpers/index.js` | Mandatory field validators per card |

---

## Edge Cases & Constraints

1. **PII replacement**: Always use synthetic test values when replacing PII. Never set PII fields to null — null values can cause the diff engine to silently skip items via mandatory field validation.

2. **Owner field pattern**: All repeater card items (Assets, Liabilities, Pensions, Protections, Family, IncomeExpenses, PowerOfAttorney) are stored under `Client1` in the DCJSON and use an `owner` field (`"Client1"`, `"Client2"`, or `"Joint"`) to indicate which client they belong to. The diff engine and change generator use this field to determine the correct client path and SF object mapping for each item.

3. **IncomeExpenses joint items**: The diff engine splits joint income/expenditure items (where `owner === "Joint"`) into two separate items, each with half the amount. Client1 keeps original ID, Client2 gets a new UUID. Amount is halved and formatted via `splitJointItem()`.

4. **POA special handling**: PowerOfAttorney data follows the same owner pattern (under `Client1`). Additionally, `mergePoAIntoWillArrangements` flattens POA fields into WillArrangements for display. The diff engine's `diffWillArrangements` then produces CREATE changes for POA items and UPDATE changes for WillArrangements fields. The sanitizer must preserve this merged structure.

5. **Network errors**: The sync functions re-throw `"Network Error"` and timeout errors (`~/Projects/DC/dcReact/app/services/changeSync/sync.js:92-93`). The test tool should catch these and report them distinctly from API-level errors.

6. **Large DCJSONs**: Sync mutations use 600s (10 minute) timeout. For meetings with 50+ repeater items, monitor for timeouts. Consider batching if needed.

7. **Joint financial items**: Joint assets/liabilities/pensions/protections produce 2 SF objects (Account + Role) instead of 1. The sObjectResolver determines this based on `isJointItem()` check.

8. **Family items always produce 2 SF objects**: `ContactAccount` + `FinServ__ContactContactRelation__c`, regardless of joint status. Joint family members create 2 Relations (one per client).

---

## CLI Commands

### `dc-sync-probe run` — Full pipeline (phases 1-5)

```bash
dc-sync-probe run -e <env> -s "<search term>" [-d <dump-dir>]
```

Runs the complete pipeline: authenticate → search & pull meeting → sanitize → diff → sync CREATE → sync UPDATE → re-pull & verify. Interactive meeting picker if multiple results.

### `dc-sync-probe sync-file` — Replay changes from file

```bash
dc-sync-probe sync-file -e <env> -s "<search term>" <changes_file.json> [-d <dump-dir>] [--no-verify]
```

Debugging command that loads a previously dumped changes file, searches for a fresh meeting, sanitizes the file's `initialDCJSON`, generates new changes via the diff engine, syncs them, and verifies. Useful for replaying and debugging specific sync scenarios without re-pulling the source meeting.

### `dc-sync-probe pull` — Phase 1 only

```bash
dc-sync-probe pull -e <env> -s "<search term>"
```

### `dc-sync-probe sanitize-cmd` — Phase 2 only

```bash
dc-sync-probe sanitize-cmd <source.json> <fresh.json> [-o <output.json>]
```

### `dc-sync-probe diff` — Phase 3 only

```bash
dc-sync-probe diff <original.json> <current.json> [-m <meeting-id>]
```

### Dump directory (`--dump-dir` / `-d`)

When provided, all intermediate JSON artifacts are saved for debugging:

| File | Contents |
|------|----------|
| `01_source_dcjson.json` | Source meeting DCJSON (or `01_fresh_dcjson.json` for sync-file) |
| `02_fresh_dcjson.json` | Fresh meeting DCJSON (target _SF values) |
| `03_sanitized_dcjson.json` | Sanitized DCJSON after Phase 2 |
| `04_create_changes.json` | CREATE changes from diff engine |
| `05_update_changes.json` | UPDATE changes from diff engine |
| `06_create_result.json` | CREATE sync mutation result |
| `07_update_result.json` | UPDATE sync mutation result |
| `08_verify_dcjson.json` | Re-pulled DCJSON after sync |
| `09_verification_report.json` | Verification report (matched/mismatches/skipped) |

---

## Verification Plan

1. **Unit-level**: Test sanitizer (PII removal, ID remapping) with a sample DCJSON
2. **Integration**: Run full flow against local/staging environment with a known test meeting
3. **Verify**: Compare re-pulled DCJSON against expected state, check all non-PII fields match
4. **Edge cases**: Empty cards, meetings with no repeater items, joint meetings with split items
