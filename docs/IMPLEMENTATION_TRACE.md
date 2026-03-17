# Implementation Trace — CLI Refactor to Match Specification

## Date: 2026-03-17

## What was done

Refactored the CLI and added new modules to align the tool with the SPECIFICATION.md document. All 3 capabilities (Clone, Apply, Replay) are now implemented as distinct CLI commands with the exact interfaces described in the spec.

## Session 2: Live testing + error handling (2026-03-17)

### SF OAuth auto-capture
- Implemented automatic OAuth code capture via temporary local HTTP server on port 3001
- When port 3001 is occupied (premeet-advisor running), prompts user to complete SF login in browser then confirm
- Spec updated to document this behavior

### Per-item sync error detection
- **Problem**: Backend reports `success: true` even when individual items fail (partial success)
- **Fix**: `sync.py` now inspects per-item results (`results[itemId].success`) and collects `item_failures`
- Top-level `success` is `false` if any item failed, regardless of backend's top-level flag
- CLI displays each failed item with its error message
- Verification still runs after sync failures to show actual meeting state
- Spec updated with "Sync Error Handling" section

### First live clone test results (gnx3+gnx2 170326, joint meeting)
- 45 CREATEs sent, 7 items failed:
  - 3x "record type missing for: Financial Account" (Investment assets without recordTypeId)
  - 2x "dataFactories[change.sObjectName] is not a function" (Emergency_Funds_Available__c)
  - 2x "Cannot read properties of undefined (reading 'filter')" (Account/employment)
- 150 UPDATEs sent, all succeeded
- These are backend-side issues, not probe bugs — the change objects we generate need further investigation

## Changes summary

### New files created

| File | Purpose |
|------|---------|
| `src/dc_sync_probe/change_sanitizer.py` | Sanitize raw production change objects: strip `isAutomated` from formData, replace PII values with synthetic data |
| `src/dc_sync_probe/change_remapper.py` | Remap IDs in production change objects. Two strategies: (1) ID-map based (deterministic, from prior clone), (2) fingerprint-based fallback (matches items by non-ID field values) |
| `tests/test_change_sanitizer.py` | Tests for change sanitization (8 tests) |
| `tests/test_change_remapper.py` | Tests for ID remapping in changes (8 tests) |
| `docs/IMPLEMENTATION_TRACE.md` | This file |

### Modified files

| File | What changed |
|------|--------------|
| `src/dc_sync_probe/cli.py` | **Full rewrite.** Replaced `run`, `sanitize_cmd`, `sync-file` commands with `clone`, `apply`, `replay` per spec. Added `-o` flag to `pull`. Kept `diff` as-is. Extracted shared helpers (`_auth`, `_find_and_pull_target`, `_sync_and_verify`, `_handle_errors`). |
| `src/dc_sync_probe/config.py` | Updated environment names to match spec: `uat`, `dc-prod`, `sjp-uat`, `sjp-prod`. Old names (`staging`, `dc_prod`, `sjp_uat`, `sjp_prod`, `feature`) kept as aliases for backward compat. |

### Deleted functionality

| Old command | Replacement |
|-------------|-------------|
| `dc-sync-probe run` | `dc-sync-probe clone --source <file>` |
| `dc-sync-probe sanitize-cmd` | Removed (was debugging helper, not in spec) |
| `dc-sync-probe sync-file` | `dc-sync-probe apply --create <file> [--update <file>]` |

## CLI commands (spec alignment)

### `dc-sync-probe clone` — Capability 1
```bash
dc-sync-probe clone -e <env> -s "<search>" --source <dcjson_file> [-d <dump-dir>]
```
- Loads source DCJSON from file
- Searches for and pulls target staging meeting
- Sanitizes source DCJSON (PII replacement, ID remapping, metadata stripping)
- Diffs sanitized vs fresh to generate changes
- Syncs creates then updates
- Verifies by re-pulling
- **Persists ID map** to dump dir (`03_id_map.json`)

### `dc-sync-probe apply` — Capability 2
```bash
dc-sync-probe apply -e <env> -s "<search>" --create <file> [--update <file>] [--id-map <file>] [-d <dump-dir>]
```
- Loads raw production change objects from log files
- Sanitizes changes (strip `isAutomated`, replace PII)
- Remaps IDs using provided ID map (deterministic) or fingerprint fallback
- Syncs creates then updates
- Verifies by re-pulling

### `dc-sync-probe replay` — Capability 3
```bash
dc-sync-probe replay -e <env> -s "<search>" --create <file> --update <file> [-d <dump-dir>]
```
- Extracts `initialDCJSON` from log files
- Runs Clone (writes to `dump/clone/` subdirectory)
- Passes ID map from clone to Apply automatically
- Runs Apply (writes to `dump/apply/` subdirectory)

### `dc-sync-probe pull` — Utility
```bash
dc-sync-probe pull -e <env> -s "<search>" [-o <output.json>]
```

### `dc-sync-probe diff` — Utility
```bash
dc-sync-probe diff <original.json> <current.json> [-m <meeting-id>]
```

## Architecture decisions

1. **Change sanitization is separate from DCJSON sanitization.** `sanitizer.py` works on full DCJSONs (Phase 2). `change_sanitizer.py` works on individual change objects (for Apply/Replay). Both share the same PII replacement values.

2. **Two ID remapping strategies.** `change_remapper.py` supports both:
   - Deterministic: uses `source_id → cloned_id` map from a prior clone
   - Fingerprint fallback: matches items by comparing non-ID field values between source and target DCJSONs

3. **Production log format handling.** `_load_changes_from_log()` handles both log formats: top-level `{changes, initialDCJSON}` and nested `{arguments: {changes, initialDCJSON}}` (the CreateChanges mutation wrapper format).

4. **Replay creates subdirectories.** When `--dump-dir` is specified for replay, clone artifacts go to `dump/clone/` and apply artifacts go to `dump/apply/` for clear separation.

5. **Environment aliases.** Spec uses `uat`, `dc-prod`, `sjp-uat`, `sjp-prod`. Old names kept as aliases so existing scripts don't break.

## Test results

224 tests passing (209 original + 15 new):
- `test_change_sanitizer.py`: 8 tests — PII replacement, isAutomated stripping, immutability
- `test_change_remapper.py`: 7 tests — ID map remapping, fingerprint matching, edge cases

## What a new agent should know

1. **The spec is the source of truth.** Always reference `docs/SPECIFICATION.md` before making changes.
2. **Core modules are stable.** `auth.py`, `transport.py`, `meeting.py`, `sanitizer.py`, `diff_engine.py`, `change_generator.py`, `sync.py`, `verify.py` — all battle-tested with comprehensive tests.
3. **The CLI orchestrates.** `cli.py` wires the modules together. Each command follows the same pattern: load inputs → auth → pull target → process → sync → verify.
4. **PII constraint is critical.** Never send real PII to staging. Both DCJSON sanitization and change sanitization enforce this.
5. **isAutomated must never appear** in sync payloads. Stripped in both `sanitizer.py` (from repeater items) and `change_sanitizer.py` (from change formData).
6. **Creates before updates.** Always. Updates may reference SF record IDs created in the create step.
7. **ID map is the bridge** between clone and apply. Without it, apply falls back to fingerprinting which is less reliable.
