# dc-sync-probe

CLI tool that replays production Salesforce sync operations against a staging environment for debugging.

See [docs/SPECIFICATION.md](docs/SPECIFICATION.md) for full requirements.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

Create `config.local.json` with your DC backend credentials:

```json
{
  "email": "your-email@example.com",
  "password": "your-password"
}
```

## Commands

### clone

Clone a production DCJSON into a staging meeting.

```bash
dc-sync-probe clone -e <env> -s "<search term>" --source <dcjson_file.json> [-d <dump-dir>]
```

Example:

```bash
dc-sync-probe clone -e local -s "Smith" --source initial_dcjson.json -d dump/clone
```

### apply

Apply production change objects to a staging meeting.

```bash
dc-sync-probe apply -e <env> -s "<search term>" --create <create_changes.json> [--update <update_changes.json>] [--id-map <id_map.json>] [-d <dump-dir>]
```

When `--id-map` is provided (e.g. from a prior `clone`), uses it for deterministic ID remapping. Without it, falls back to data fingerprinting.

### replay

Full production debugging workflow: clone + apply in sequence.

```bash
dc-sync-probe replay -e <env> -s "<search term>" --create <create_changes.json> --update <update_changes.json> [-d <dump-dir>]
```

Extracts `initialDCJSON` from the log files, clones the meeting to match, then applies the changes using the ID map from clone.

### pull

Pull a meeting's DCJSON.

```bash
dc-sync-probe pull -e <env> -s "<search term>" [-o <output.json>]
```

### diff

Diff two DCJSONs and show generated changes.

```bash
dc-sync-probe diff <original.json> <current.json> [-m <meeting-id>]
```

## Environments

| Name | Description |
|------|-------------|
| `local` | localhost:3000 |
| `dev` | Dev environment |
| `uat` | UAT / staging |
| `dc-prod` | DC production |
| `sjp-uat` | SJP UAT |
| `sjp-prod` | SJP production |

## Running tests

```bash
pytest
```

## Production log file format

The tool expects production log files in this format:

**CreateChanges:**
```json
{
  "operation": "mutation",
  "arguments": {
    "meetingId": "uuid",
    "changes": [...],
    "initialDCJSON": {...},
    "currentDCJSON": {...},
    "source": "ios"
  }
}
```

**UpdateChanges:**
```json
{
  "meetingId": "uuid",
  "changes": [...],
  "initialDCJSON": {...},
  "currentDCJSON": {...},
  "source": "ios"
}
```

## Dump artifacts

When `-d <dump-dir>` is specified, all intermediate JSON is saved with numbered filenames for clear ordering. This includes source data, sanitized data, generated changes, sync results, and verification reports.
