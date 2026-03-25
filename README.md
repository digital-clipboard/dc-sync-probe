# dc-sync-probe

A command-line tool for replaying Salesforce sync operations from production against a staging environment. This is useful for debugging sync issues — you take the data from a real production sync and replay it in a safe staging environment to see what happens.

---

## Prerequisites

You need **Python 3.11 or newer** installed on your machine.

**Check your Python version** by opening a terminal and running:

```bash
python3 --version
```

If you see something like `Python 3.11.x` or higher, you're good to go. If not, install Python from [python.org](https://www.python.org/downloads/).

You also need **Git** to download the project. Check with:

```bash
git --version
```

---

## Installation (step by step)

### 1. Download the project

Open a terminal and run:

```bash
git clone <repository-url>
cd dc-sync-probe
```

Replace `<repository-url>` with the actual URL of this repository.

### 2. Create a virtual environment

This keeps the tool's dependencies isolated from the rest of your system:

```bash
python3 -m venv .venv
```

### 3. Activate the virtual environment

**Mac / Linux:**

```bash
source .venv/bin/activate
```

**Windows (Command Prompt):**

```cmd
.venv\Scripts\activate
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\Activate.ps1
```

You should see `(.venv)` appear at the beginning of your terminal prompt. This means the virtual environment is active.

### 4. Install the tool

```bash
pip install -e .
```

This installs the `dc-sync-probe` command so you can use it from anywhere (while the virtual environment is active).

### 5. Set up your credentials

Create a file called `config.local.json` in the project folder with your DC backend login:

```json
{
  "email": "your-email@example.com",
  "password": "your-password"
}
```

> **Important:** This file contains your password. It is already listed in `.gitignore` so it won't be committed, but keep it safe.

---

## How to use

Every time you open a new terminal, you need to activate the virtual environment first:

```bash
cd dc-sync-probe
source .venv/bin/activate
```

Then you can run any of the commands below.

### Choosing an environment

Every command requires an environment (`-e`). These are the available environments:

| Flag value | What it points to |
|------------|-------------------|
| `local` | Your local dev server (localhost:3000) |
| `dev` | Shared development environment |
| `uat` | UAT / staging environment |
| `dc-prod` | DC production (use with caution) |
| `sjp-uat` | SJP UAT environment |
| `sjp-prod` | SJP production (use with caution) |

For debugging, you'll typically use `local`, `dev`, or `uat`.

---

### Command: `clone`

**What it does:** Takes a production DCJSON file and copies its data into an existing staging meeting. This sets up the staging meeting to look like the production one.

**When to use it:** You have a DCJSON snapshot from production and you want to replicate that meeting state in staging.

```bash
dc-sync-probe clone -e <environment> -s "<client name>" --source <dcjson_file.json>
```

**Example:**

```bash
dc-sync-probe clone -e uat -s "Smith" --source initial_dcjson.json -d dump/clone
```

This will:
1. Load the production DCJSON from `initial_dcjson.json`
2. Search for a meeting with "Smith" in the UAT environment
3. Overwrite that meeting's data to match the production snapshot
4. Save all intermediate files to `dump/clone/` (optional, for inspection)

---

### Command: `apply`

**What it does:** Takes production change objects (create/update operations from logs) and applies them to a staging meeting.

**When to use it:** You have production log files containing the sync changes that caused a problem, and you want to replay just those changes against a staging meeting.

```bash
dc-sync-probe apply -e <environment> -s "<client name>" --create <create_changes.json> --update <update_changes.json>
```

**Example (with ID map from a prior clone):**

```bash
dc-sync-probe apply -e uat -s "Smith" \
  --create create_log.json \
  --update update_log.json \
  --id-map dump/clone/03_id_map.json \
  -d dump/apply
```

The `--id-map` option uses the ID mapping from a previous `clone` to correctly translate production IDs to staging IDs. If you don't provide it, the tool will try to figure out the mapping automatically (fingerprinting), which works in most cases.

---

### Command: `replay`

**What it does:** Runs `clone` followed by `apply` in one step. This is the most common workflow for debugging a production sync issue end-to-end.

**When to use it:** You have the full production log files and want to reproduce the entire sync scenario in staging.

```bash
dc-sync-probe replay -e <environment> -s "<client name>" --create <create_log.json> --update <update_log.json>
```

**Example:**

```bash
dc-sync-probe replay -e uat -s "Smith" \
  --create create_log.json \
  --update update_log.json \
  -d dump/replay
```

This will:
1. Extract `initialDCJSON` from the log files
2. Clone that state into the staging meeting
3. Apply the changes from the logs
4. Verify the result

---

### Command: `pull`

**What it does:** Downloads a meeting's current DCJSON from any environment.

**When to use it:** You want to inspect what a meeting looks like right now, or save it to a file for comparison.

```bash
dc-sync-probe pull -e <environment> -s "<client name>"
```

**Example (save to file):**

```bash
dc-sync-probe pull -e uat -s "Smith" -o meeting_snapshot.json
```

---

### Command: `diff`

**What it does:** Compares two DCJSON files and shows what changes would be generated to go from one to the other.

**When to use it:** You have two snapshots of a meeting and want to understand what changed between them.

```bash
dc-sync-probe diff original.json current.json
```

---

## Saving debug artifacts

Most commands accept a `-d <folder>` option. When used, the tool saves every intermediate step as numbered JSON files in that folder. This is useful for understanding what happened at each stage:

```
dump/clone/
  01_source_dcjson.json        # The input data
  02_fresh_dcjson.json         # The staging meeting before changes
  03_sanitized_dcjson.json     # After cleaning/remapping
  03_id_map.json               # Production-to-staging ID mapping
  04_create_changes.json       # Generated create operations
  05_update_changes.json       # Generated update operations
  06_create_result.json        # Server response for creates
  06_update_result.json        # Server response for updates
  06_verify_dcjson.json        # Meeting state after sync
  06_verification_report.json  # Pass/fail comparison
```

---

## Production log file format

The tool expects log files in one of these formats:

**CreateChanges log:**

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

**UpdateChanges log:**

```json
{
  "meetingId": "uuid",
  "changes": [...],
  "initialDCJSON": {...},
  "currentDCJSON": {...},
  "source": "ios"
}
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `command not found: dc-sync-probe` | Make sure your virtual environment is activated (`source .venv/bin/activate`) |
| `Session expired` error | Your login token expired. Just run the command again — it will re-authenticate |
| `Transport error` | Check your network connection and that the target environment is reachable |
| `No initialDCJSON found` | The log file you provided doesn't contain the expected `initialDCJSON` field |
| `Mismatch: source is joint but target is single-client` | The staging meeting type (single vs joint client) doesn't match the production data. Find a matching meeting |

---

## Running tests (for developers)

```bash
pip install -e ".[test]"
pytest
```
