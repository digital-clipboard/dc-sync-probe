"""CLI entry point — implements clone, apply, replay, pull, diff per specification."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from .auth import ensure_salesforce_auth, login_email_password
from .change_remapper import (
    build_fingerprint_id_map,
    remap_changes_with_id_map,
)
from .change_sanitizer import sanitize_changes
from .config import ENVIRONMENTS, Session
from .diff_engine import generate_all_changes
from .meeting import find_and_pull, pull_meeting, transform_dcjson
from .sanitizer import sanitize
from .sync import sync_create_changes, sync_update_changes
from .transport import SessionExpiredError, TransportError
from .verify import print_report, verify

console = Console()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _dump_json(dump: Path | None, name: str, data: dict | list) -> None:
    if dump:
        path = dump / name
        path.write_text(json.dumps(data, indent=2, default=str))
        console.print(f"  [dim]Dumped -> {path}[/dim]")


def _print_sync_failures(op: str, result: dict) -> None:
    """Print per-item sync failures."""
    failures = result.get("item_failures", [])
    if failures:
        console.print(
            f"  [bold red]{op} sync FAILED:[/bold red] "
            f"{len(failures)} item(s) failed"
        )
        for f in failures:
            console.print(f"    [red]{f['id'][:12]}...[/red] {f['error']}")
    else:
        console.print(
            f"  [bold red]{op} sync FAILED:[/bold red] {result['message']}"
        )


def _handle_errors(fn):
    """Decorator: catch common errors and exit cleanly."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SessionExpiredError as exc:
            console.print(f"\n[bold red]Session expired:[/bold red] {exc}")
            sys.exit(1)
        except TransportError as exc:
            console.print(f"\n[bold red]Transport error:[/bold red] {exc}")
            sys.exit(1)
        except KeyboardInterrupt:
            console.print("\n[dim]Aborted.[/dim]")
            sys.exit(130)
    return wrapper


def _is_joint_dcjson(dcjson: dict) -> bool:
    """Check if a DCJSON represents a joint (two-client) meeting."""
    c2 = (dcjson.get("PersonalDetails") or {}).get("Client2", {})
    return bool(c2.get("firstName") or c2.get("lastName"))


def _validate_meeting_compatibility(
    source_dcjson: dict, target_dcjson: dict, label: str = "source",
) -> None:
    """Fail if source and target have different client structures."""
    source_joint = _is_joint_dcjson(source_dcjson)
    target_joint = _is_joint_dcjson(target_dcjson)
    if source_joint != target_joint:
        source_type = "joint" if source_joint else "single-client"
        target_type = "joint" if target_joint else "single-client"
        console.print(
            f"[bold red]Mismatch:[/bold red] {label} is {source_type} "
            f"but target meeting is {target_type}. "
            f"Cannot sync incompatible meeting types."
        )
        sys.exit(1)
    meeting_type = "joint" if source_joint else "single-client"
    console.print(f"  Meeting type: [bold]{meeting_type}[/bold] (matches)")


def _auth(session: Session) -> None:
    console.print(Panel("[bold]Authentication[/bold]"))
    login_email_password(session)
    ensure_salesforce_auth(session)


def _find_and_pull_target(session: Session, search_term: str) -> dict:
    """Search, pick, pull, and transform a target meeting."""
    console.print(Panel("[bold]Find & Pull Target Meeting[/bold]"))
    result = find_and_pull(session, search_term)
    meeting_id = result["meetingId"]
    swift1 = result["sfAccountId"]
    swift2 = result.get("sfAccountId2") or ""
    console.print(f"  Meeting ID : [bold]{meeting_id}[/bold]")
    console.print(f"  Swift1     : [bold]{swift1}[/bold]")
    if swift2:
        console.print(f"  Swift2     : [bold]{swift2}[/bold]")
    return result


def _sync_and_verify(
    session: Session,
    meeting_id: str,
    create_changes: list[dict],
    update_changes: list[dict],
    initial_dcjson: dict,
    current_dcjson: dict,
    swift1: str,
    swift2: str,
    expected_dcjson: dict,
    dump: Path | None,
    dump_prefix: str = "",
) -> dict | None:
    """Sync creates+updates, then verify. Returns verification report."""
    # ── Sync ──
    console.print(Panel("[bold]Sync Changes[/bold]"))
    has_failures = False

    create_result = sync_create_changes(
        session, meeting_id, create_changes, initial_dcjson, current_dcjson,
    )
    _dump_json(dump, f"{dump_prefix}create_result.json", create_result)
    if not create_result["success"]:
        has_failures = True
        _print_sync_failures("CREATE", create_result)
    else:
        console.print(f"  [green]CREATE sync OK[/green]: {create_result['message']}")

    update_result = sync_update_changes(
        session, meeting_id, update_changes, initial_dcjson, current_dcjson,
    )
    _dump_json(dump, f"{dump_prefix}update_result.json", update_result)
    if not update_result["success"]:
        has_failures = True
        _print_sync_failures("UPDATE", update_result)
    else:
        console.print(f"  [green]UPDATE sync OK[/green]: {update_result['message']}")

    if has_failures:
        console.print(
            "\n[bold yellow]Sync had failures -- "
            "proceeding to verification to show actual state.[/bold yellow]"
        )

    # ── Verify ──
    console.print(Panel("[bold]Verify[/bold]"))
    console.print("Re-pulling meeting from Salesforce...")
    verify_result = pull_meeting(session, swift1, swift2, meeting_id)
    verify_dcjson = transform_dcjson(verify_result["DCJSON"])
    _dump_json(dump, f"{dump_prefix}verify_dcjson.json", verify_dcjson)

    report = verify(expected_dcjson, verify_dcjson)
    report["sync_had_failures"] = has_failures
    _dump_json(dump, f"{dump_prefix}verification_report.json", report)
    print_report(report)

    if has_failures:
        console.print(
            "\n[bold red]RESULT: FAIL[/bold red] -- "
            "sync completed with errors (see above)"
        )
    return report


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """dc-sync-probe -- replay production sync operations against staging."""


# ---------------------------------------------------------------------------
# clone — Capability 1
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--env", "-e",
    type=click.Choice(list(ENVIRONMENTS), case_sensitive=False),
    required=True,
    help="Target environment.",
)
@click.option("--search", "-s", required=True, help="Client name to search for.")
@click.option(
    "--source",
    type=click.Path(exists=True),
    required=True,
    help="Source DCJSON file (e.g. initialDCJSON from production logs).",
)
@click.option(
    "--dump-dir", "-d",
    type=click.Path(),
    default=None,
    help="Directory to save intermediate artifacts.",
)
def clone(env: str, search: str, source: str, dump_dir: str | None) -> None:
    """Clone a source DCJSON into a staging meeting."""
    session = Session(env)
    dump = Path(dump_dir) if dump_dir else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)

    @_handle_errors
    def _run():
        _clone_pipeline(session, search, Path(source), dump)

    _run()


def _clone_pipeline(
    session: Session,
    search_term: str,
    source_path: Path,
    dump: Path | None,
) -> tuple[dict[str, str], dict]:
    """Execute clone pipeline. Returns (id_map, meeting_info)."""

    # ── Load source DCJSON ──
    console.print(Panel(f"[bold]Loading source DCJSON from {source_path.name}[/bold]"))
    source_dcjson = json.loads(source_path.read_text())
    _dump_json(dump, "01_source_dcjson.json", source_dcjson)

    # ── Auth ──
    _auth(session)

    # ── Find & Pull target meeting ──
    target = _find_and_pull_target(session, search_term)
    fresh_dcjson = target["DCJSON"]
    meeting_id = target["meetingId"]
    swift1 = target["sfAccountId"]
    swift2 = target.get("sfAccountId2") or ""
    _dump_json(dump, "02_fresh_dcjson.json", fresh_dcjson)

    # ── Validate compatibility ──
    _validate_meeting_compatibility(source_dcjson, fresh_dcjson, label="source DCJSON")

    # ── Sanitize ──
    console.print(Panel("[bold]Sanitize Source DCJSON[/bold]"))
    sanitized, id_map = sanitize(source_dcjson, fresh_dcjson, return_id_map=True)
    _dump_json(dump, "03_sanitized_dcjson.json", sanitized)
    _dump_json(dump, "03_id_map.json", id_map)
    console.print(f"  IDs remapped: [bold]{len(id_map)}[/bold]")

    # ── Generate changes ──
    console.print(Panel("[bold]Generate Changes[/bold]"))
    create_changes, update_changes = generate_all_changes(
        fresh_dcjson, sanitized, meeting_id,
    )
    console.print(
        f"  CREATE changes: [bold]{len(create_changes)}[/bold]  |  "
        f"UPDATE changes: [bold]{len(update_changes)}[/bold]"
    )
    _dump_json(dump, "04_create_changes.json", create_changes)
    _dump_json(dump, "05_update_changes.json", update_changes)

    if not create_changes and not update_changes:
        console.print("[yellow]No changes generated -- nothing to sync.[/yellow]")
        return id_map, target

    # ── Sync & Verify ──
    _sync_and_verify(
        session, meeting_id,
        create_changes, update_changes,
        fresh_dcjson, sanitized,
        swift1, swift2,
        expected_dcjson=sanitized,
        dump=dump,
        dump_prefix="06_",
    )

    return id_map, target


# ---------------------------------------------------------------------------
# apply — Capability 2
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--env", "-e",
    type=click.Choice(list(ENVIRONMENTS), case_sensitive=False),
    required=True,
    help="Target environment.",
)
@click.option("--search", "-s", required=True, help="Client name to search for.")
@click.option(
    "--create",
    "create_file",
    type=click.Path(exists=True),
    default=None,
    help="Create changes JSON file (production log format).",
)
@click.option(
    "--update",
    "update_file",
    type=click.Path(exists=True),
    default=None,
    help="Update changes JSON file (production log format).",
)
@click.option(
    "--id-map",
    "id_map_file",
    type=click.Path(exists=True),
    default=None,
    help="ID map JSON from a prior clone (source_id -> cloned_id).",
)
@click.option(
    "--dump-dir", "-d",
    type=click.Path(),
    default=None,
    help="Directory to save intermediate artifacts.",
)
def apply(
    env: str, search: str,
    create_file: str | None, update_file: str | None,
    id_map_file: str | None, dump_dir: str | None,
) -> None:
    """Apply production change objects to a staging meeting."""
    if not create_file and not update_file:
        raise click.UsageError("At least one of --create or --update is required.")

    session = Session(env)
    dump = Path(dump_dir) if dump_dir else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)

    @_handle_errors
    def _run():
        _apply_pipeline(
            session, search,
            Path(create_file) if create_file else None,
            Path(update_file) if update_file else None,
            Path(id_map_file) if id_map_file else None,
            dump,
        )

    _run()


def _load_changes_from_log(path: Path) -> tuple[list[dict], dict]:
    """Load changes and initialDCJSON from a production log file."""
    payload = json.loads(path.read_text())
    # Handle both formats: top-level changes or nested in arguments
    if "arguments" in payload:
        args = payload["arguments"]
        changes = args.get("changes", [])
        initial = args.get("initialDCJSON", {})
    else:
        changes = payload.get("changes", [])
        initial = payload.get("initialDCJSON", {})
    return changes, initial


def _apply_pipeline(
    session: Session,
    search_term: str,
    create_path: Path | None,
    update_path: Path | None,
    id_map_path: Path | None,
    dump: Path | None,
) -> None:
    """Execute apply pipeline."""

    # ── Load change files ──
    console.print(Panel("[bold]Loading Change Files[/bold]"))
    raw_creates: list[dict] = []
    raw_updates: list[dict] = []
    initial_dcjson: dict = {}

    if create_path:
        raw_creates, initial_dcjson = _load_changes_from_log(create_path)
        console.print(f"  Create changes: [bold]{len(raw_creates)}[/bold]")
    if update_path:
        raw_updates, upd_initial = _load_changes_from_log(update_path)
        if not initial_dcjson:
            initial_dcjson = upd_initial
        console.print(f"  Update changes: [bold]{len(raw_updates)}[/bold]")

    _dump_json(dump, "01_raw_create_changes.json", raw_creates)
    _dump_json(dump, "01_raw_update_changes.json", raw_updates)

    # ── Load ID map if provided ──
    id_map: dict[str, str] | None = None
    if id_map_path:
        id_map = json.loads(id_map_path.read_text())
        console.print(f"  ID map loaded: [bold]{len(id_map)}[/bold] entries")

    # ── Sanitize changes ──
    console.print(Panel("[bold]Sanitize Changes[/bold]"))
    creates = sanitize_changes(raw_creates)
    updates = sanitize_changes(raw_updates)
    console.print("  Stripped isAutomated, replaced PII in formData")
    _dump_json(dump, "02_sanitized_create_changes.json", creates)
    _dump_json(dump, "02_sanitized_update_changes.json", updates)

    # ── Auth ──
    _auth(session)

    # ── Find & Pull target meeting ──
    target = _find_and_pull_target(session, search_term)
    fresh_dcjson = target["DCJSON"]
    meeting_id = target["meetingId"]
    swift1 = target["sfAccountId"]
    swift2 = target.get("sfAccountId2") or ""
    _dump_json(dump, "03_fresh_dcjson.json", fresh_dcjson)

    # ── Validate compatibility ──
    if initial_dcjson:
        _validate_meeting_compatibility(initial_dcjson, fresh_dcjson, label="change files")

    # ── Remap IDs ──
    console.print(Panel("[bold]Remap IDs in Changes[/bold]"))
    if id_map:
        console.print("  Using ID map from prior clone (deterministic)")
    else:
        console.print("  No ID map provided -- falling back to data fingerprinting")
        id_map = build_fingerprint_id_map(initial_dcjson, fresh_dcjson)
        console.print(f"  Fingerprint matched: [bold]{len(id_map)}[/bold] items")

    _dump_json(dump, "04_id_map.json", id_map)

    creates = remap_changes_with_id_map(creates, id_map, meeting_id)
    updates = remap_changes_with_id_map(updates, id_map, meeting_id)
    _dump_json(dump, "05_remapped_create_changes.json", creates)
    _dump_json(dump, "05_remapped_update_changes.json", updates)

    console.print(
        f"  CREATE: [bold]{len(creates)}[/bold]  |  "
        f"UPDATE: [bold]{len(updates)}[/bold]"
    )

    if not creates and not updates:
        console.print("[yellow]No changes to apply.[/yellow]")
        return

    # ── Sync & Verify ──
    # For apply, use fresh_dcjson as both initial and expected basis
    _sync_and_verify(
        session, meeting_id,
        creates, updates,
        fresh_dcjson, fresh_dcjson,
        swift1, swift2,
        expected_dcjson=fresh_dcjson,
        dump=dump,
        dump_prefix="06_",
    )


# ---------------------------------------------------------------------------
# replay — Capability 3 (compose clone + apply)
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--env", "-e",
    type=click.Choice(list(ENVIRONMENTS), case_sensitive=False),
    required=True,
    help="Target environment.",
)
@click.option("--search", "-s", required=True, help="Client name to search for.")
@click.option(
    "--create",
    "create_file",
    type=click.Path(exists=True),
    required=True,
    help="CreateChanges JSON file (production log).",
)
@click.option(
    "--update",
    "update_file",
    type=click.Path(exists=True),
    required=True,
    help="UpdateChanges JSON file (production log).",
)
@click.option(
    "--dump-dir", "-d",
    type=click.Path(),
    default=None,
    help="Directory to save intermediate artifacts.",
)
def replay(
    env: str, search: str,
    create_file: str, update_file: str,
    dump_dir: str | None,
) -> None:
    """Replay production sync: clone initialDCJSON then apply changes."""
    session = Session(env)
    dump = Path(dump_dir) if dump_dir else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)

    @_handle_errors
    def _run():
        _replay_pipeline(
            session, search,
            Path(create_file), Path(update_file),
            dump,
        )

    _run()


def _replay_pipeline(
    session: Session,
    search_term: str,
    create_path: Path,
    update_path: Path,
    dump: Path | None,
) -> None:
    """Execute replay pipeline: clone then apply."""

    # ── Extract initialDCJSON from log files ──
    console.print(Panel("[bold]Loading Production Log Files[/bold]"))
    raw_creates, create_initial = _load_changes_from_log(create_path)
    raw_updates, update_initial = _load_changes_from_log(update_path)
    initial_dcjson = create_initial or update_initial

    if not initial_dcjson:
        console.print("[bold red]No initialDCJSON found in log files.[/bold red]")
        sys.exit(1)

    console.print(f"  Create changes: [bold]{len(raw_creates)}[/bold]")
    console.print(f"  Update changes: [bold]{len(raw_updates)}[/bold]")
    console.print(f"  initialDCJSON: [bold]present[/bold]")

    # ── Write initialDCJSON to temp file for clone ──
    clone_dump = dump / "clone" if dump else None
    apply_dump = dump / "apply" if dump else None
    if clone_dump:
        clone_dump.mkdir(parents=True, exist_ok=True)
    if apply_dump:
        apply_dump.mkdir(parents=True, exist_ok=True)

    # Save initialDCJSON as source for clone
    source_path = (dump or Path(".")) / "_initial_dcjson.json"
    source_path.write_text(json.dumps(initial_dcjson, indent=2, default=str))

    # ── Step 1: Clone ──
    console.print(Panel("[bold cyan]Step 1: Clone[/bold cyan]"))
    id_map, target = _clone_pipeline(session, search_term, source_path, clone_dump)

    # Clean up temp file
    if source_path.exists() and not dump:
        source_path.unlink()

    meeting_id = target["meetingId"]
    swift1 = target["sfAccountId"]
    swift2 = target.get("sfAccountId2") or ""

    # ── Step 2: Apply Changes ──
    console.print(Panel("[bold cyan]Step 2: Apply Changes[/bold cyan]"))

    # Sanitize changes
    creates = sanitize_changes(raw_creates)
    updates = sanitize_changes(raw_updates)
    _dump_json(apply_dump, "01_sanitized_create_changes.json", creates)
    _dump_json(apply_dump, "01_sanitized_update_changes.json", updates)

    # Remap using ID map from clone (deterministic)
    console.print(f"  Remapping IDs using clone ID map ({len(id_map)} entries)")
    creates = remap_changes_with_id_map(creates, id_map, meeting_id)
    updates = remap_changes_with_id_map(updates, id_map, meeting_id)
    _dump_json(apply_dump, "02_remapped_create_changes.json", creates)
    _dump_json(apply_dump, "02_remapped_update_changes.json", updates)

    console.print(
        f"  CREATE: [bold]{len(creates)}[/bold]  |  "
        f"UPDATE: [bold]{len(updates)}[/bold]"
    )

    if not creates and not updates:
        console.print("[yellow]No changes to apply.[/yellow]")
        return

    # Pull fresh state after clone for the sync context
    console.print("Re-pulling meeting after clone for sync context...")
    post_clone = pull_meeting(session, swift1, swift2, meeting_id)
    post_clone_dcjson = transform_dcjson(post_clone["DCJSON"])
    _dump_json(apply_dump, "03_post_clone_dcjson.json", post_clone_dcjson)

    # Sync & verify
    _sync_and_verify(
        session, meeting_id,
        creates, updates,
        post_clone_dcjson, post_clone_dcjson,
        swift1, swift2,
        expected_dcjson=post_clone_dcjson,
        dump=apply_dump,
        dump_prefix="04_",
    )


# ---------------------------------------------------------------------------
# pull — Utility
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--env", "-e",
    type=click.Choice(list(ENVIRONMENTS), case_sensitive=False),
    required=True,
    help="Target environment.",
)
@click.option("--search", "-s", required=True, help="Client name to search for.")
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file path for the DCJSON.",
)
def pull(env: str, search: str, output: str | None) -> None:
    """Pull a meeting's DCJSON."""
    session = Session(env)

    @_handle_errors
    def _run():
        _auth(session)
        result = find_and_pull(session, search)
        dcjson = result["DCJSON"]
        out = json.dumps(dcjson, indent=2, default=str)
        if output:
            Path(output).write_text(out)
            console.print(f"Written to {output}")
        else:
            console.print_json(out[:5000])

    _run()


# ---------------------------------------------------------------------------
# diff — Utility
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("original_json", type=click.Path(exists=True))
@click.argument("current_json", type=click.Path(exists=True))
@click.option("--meeting-id", "-m", default="test-meeting-id")
def diff(original_json: str, current_json: str, meeting_id: str) -> None:
    """Diff two DCJSONs and show the generated changes."""
    orig = json.loads(Path(original_json).read_text())
    cur = json.loads(Path(current_json).read_text())
    creates, updates = generate_all_changes(orig, cur, meeting_id)
    console.print(f"CREATE changes: {len(creates)}")
    console.print(f"UPDATE changes: {len(updates)}")
    for c in creates[:10]:
        console.print(f"  [green]CREATE[/green] {c['slag']}")
    for u in updates[:10]:
        console.print(f"  [yellow]UPDATE[/yellow] {u['slag']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
