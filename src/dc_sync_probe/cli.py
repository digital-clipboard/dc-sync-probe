"""CLI entry point — orchestrates the full 5-phase sync test pipeline."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from .auth import ensure_salesforce_auth, login_email_password
from .config import ENVIRONMENTS, Session
from .diff_engine import generate_all_changes
from .meeting import find_and_pull, pull_meeting, transform_dcjson
from .sanitizer import sanitize
from .sync import sync_create_changes, sync_update_changes
from .transport import SessionExpiredError, TransportError
from .verify import print_report, verify

console = Console()


@click.group()
def cli() -> None:
    """dc-sync-probe — end-to-end DC sync pipeline tester."""


@cli.command()
@click.option(
    "--env", "-e",
    type=click.Choice(list(ENVIRONMENTS), case_sensitive=False),
    required=True,
    help="Backend environment to target.",
)
@click.option("--search", "-s", required=True, help="Client name to search for.")
@click.option(
    "--dump-dir", "-d",
    type=click.Path(),
    default=None,
    help="Directory to dump intermediate JSON artifacts for debugging.",
)
def run(env: str, search: str, dump_dir: str | None) -> None:
    """Run the full sync test pipeline (phases 1-5)."""
    session = Session(env)
    dump = Path(dump_dir) if dump_dir else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)

    try:
        _run_pipeline(session, search, dump)
    except SessionExpiredError as exc:
        console.print(f"\n[bold red]Session expired:[/bold red] {exc}")
        sys.exit(1)
    except TransportError as exc:
        console.print(f"\n[bold red]Transport error:[/bold red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Aborted.[/dim]")
        sys.exit(130)


def _dump_json(dump: Path | None, name: str, data: dict) -> None:
    if dump:
        path = dump / name
        path.write_text(json.dumps(data, indent=2, default=str))
        console.print(f"  [dim]Dumped → {path}[/dim]")


def _run_pipeline(session: Session, search_term: str, dump: Path | None) -> None:
    # ── Auth ──────────────────────────────────────────────────────────
    console.print(Panel("[bold]Phase 0: Authentication[/bold]"))
    login_email_password(session)
    ensure_salesforce_auth(session)

    # ── Phase 1: Find & Pull ──────────────────────────────────────────
    console.print(Panel("[bold]Phase 1: Find & Pull Meeting[/bold]"))
    source = find_and_pull(session, search_term)
    source_dcjson = source["DCJSON"]
    meeting_id = source["meetingId"]
    swift1 = source["sfAccountId"]
    swift2 = source.get("sfAccountId2") or ""
    console.print(f"  Meeting ID : [bold]{meeting_id}[/bold]")
    console.print(f"  Swift1     : [bold]{swift1}[/bold]")
    if swift2:
        console.print(f"  Swift2     : [bold]{swift2}[/bold]")
    _dump_json(dump, "01_source_dcjson.json", source_dcjson)

    # Pull a "fresh" meeting (same SF accounts → same meeting in SF)
    console.print("\n[bold]Pulling fresh meeting for target _SF values…[/bold]")
    fresh_result = pull_meeting(session, swift1, swift2, meeting_id)
    fresh_dcjson = transform_dcjson(fresh_result["DCJSON"])
    _dump_json(dump, "02_fresh_dcjson.json", fresh_dcjson)

    # ── Phase 2: Sanitize ─────────────────────────────────────────────
    console.print(Panel("[bold]Phase 2: Sanitize DCJSON[/bold]"))
    sanitized = sanitize(source_dcjson, fresh_dcjson)
    _dump_json(dump, "03_sanitized_dcjson.json", sanitized)
    console.print("[green]Sanitization complete.[/green]")

    # ── Phase 3: Generate changes ─────────────────────────────────────
    console.print(Panel("[bold]Phase 3: Generate Changes[/bold]"))
    create_changes, update_changes = generate_all_changes(
        fresh_dcjson, sanitized, meeting_id,
    )
    console.print(
        f"  CREATE changes: [bold]{len(create_changes)}[/bold]  |  "
        f"UPDATE changes: [bold]{len(update_changes)}[/bold]"
    )
    _dump_json(dump, "04_create_changes.json", {"changes": create_changes})
    _dump_json(dump, "05_update_changes.json", {"changes": update_changes})

    if not create_changes and not update_changes:
        console.print("[yellow]No changes generated — nothing to sync.[/yellow]")
        return

    # ── Phase 4: Sync ─────────────────────────────────────────────────
    console.print(Panel("[bold]Phase 4: Sync Changes[/bold]"))

    create_result = sync_create_changes(
        session, meeting_id, create_changes, fresh_dcjson, sanitized,
    )
    if not create_result["success"]:
        console.print(f"[bold red]CREATE sync failed:[/bold red] {create_result['message']}")
        _dump_json(dump, "06_create_result.json", create_result)
        return
    console.print(f"  [green]CREATE sync OK[/green]: {create_result['message']}")
    _dump_json(dump, "06_create_result.json", create_result)

    update_result = sync_update_changes(
        session, meeting_id, update_changes, fresh_dcjson, sanitized,
    )
    if not update_result["success"]:
        console.print(f"[bold red]UPDATE sync failed:[/bold red] {update_result['message']}")
        _dump_json(dump, "07_update_result.json", update_result)
        return
    console.print(f"  [green]UPDATE sync OK[/green]: {update_result['message']}")
    _dump_json(dump, "07_update_result.json", update_result)

    # ── Phase 5: Verify ───────────────────────────────────────────────
    console.print(Panel("[bold]Phase 5: Verify[/bold]"))
    console.print("Re-pulling meeting from Salesforce…")
    verify_result = pull_meeting(session, swift1, swift2, meeting_id)
    verify_dcjson = transform_dcjson(verify_result["DCJSON"])
    _dump_json(dump, "08_verify_dcjson.json", verify_dcjson)

    report = verify(sanitized, verify_dcjson)
    _dump_json(dump, "09_verification_report.json", report)
    print_report(report)


# ---------------------------------------------------------------------------
# Standalone sub-commands for individual phases (handy for debugging)
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--env", "-e", type=click.Choice(list(ENVIRONMENTS), case_sensitive=False), required=True)
@click.option("--search", "-s", required=True)
def pull(env: str, search: str) -> None:
    """Phase 1 only: search, pick, and pull a meeting."""
    session = Session(env)
    login_email_password(session)
    ensure_salesforce_auth(session)
    result = find_and_pull(session, search)
    console.print_json(json.dumps(result["DCJSON"], indent=2, default=str)[:5000])


@cli.command()
@click.argument("source_json", type=click.Path(exists=True))
@click.argument("fresh_json", type=click.Path(exists=True))
@click.option("--out", "-o", type=click.Path(), default=None)
def sanitize_cmd(source_json: str, fresh_json: str, out: str | None) -> None:
    """Phase 2 only: sanitize a source DCJSON given a fresh DCJSON."""
    src = json.loads(Path(source_json).read_text())
    fresh = json.loads(Path(fresh_json).read_text())
    result = sanitize(src, fresh)
    output = json.dumps(result, indent=2, default=str)
    if out:
        Path(out).write_text(output)
        console.print(f"Written to {out}")
    else:
        console.print_json(output[:5000])


@cli.command()
@click.argument("original_json", type=click.Path(exists=True))
@click.argument("current_json", type=click.Path(exists=True))
@click.option("--meeting-id", "-m", default="test-meeting-id")
def diff(original_json: str, current_json: str, meeting_id: str) -> None:
    """Phase 3 only: diff two DCJSONs and show the generated changes."""
    orig = json.loads(Path(original_json).read_text())
    cur = json.loads(Path(current_json).read_text())
    creates, updates = generate_all_changes(orig, cur, meeting_id)
    console.print(f"CREATE changes: {len(creates)}")
    console.print(f"UPDATE changes: {len(updates)}")
    for c in creates[:10]:
        console.print(f"  [green]CREATE[/green] {c['slag']}")
    for u in updates[:10]:
        console.print(f"  [yellow]UPDATE[/yellow] {u['slag']}")


@cli.command("sync-file")
@click.option(
    "--env", "-e",
    type=click.Choice(list(ENVIRONMENTS), case_sensitive=False),
    required=True,
    help="Backend environment to target.",
)
@click.option("--search", "-s", required=True, help="Client name to search for.")
@click.argument("changes_file", type=click.Path(exists=True))
@click.option(
    "--dump-dir", "-d",
    type=click.Path(),
    default=None,
    help="Directory to dump intermediate JSON artifacts for debugging.",
)
@click.option(
    "--verify/--no-verify", "do_verify",
    default=True,
    help="Re-pull and verify after sync.",
)
def sync_file(
    env: str, search: str, changes_file: str,
    dump_dir: str | None, do_verify: bool,
) -> None:
    """Search + pull a real meeting, then replay changes from a file.

    Searches for the meeting on the backend, pulls the real DCJSON,
    remaps the file's changes to match the real item IDs, then syncs.
    """
    session = Session(env)
    dump = Path(dump_dir) if dump_dir else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)

    try:
        _run_sync_file(session, search, Path(changes_file), dump, do_verify)
    except SessionExpiredError as exc:
        console.print(f"\n[bold red]Session expired:[/bold red] {exc}")
        sys.exit(1)
    except TransportError as exc:
        console.print(f"\n[bold red]Transport error:[/bold red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Aborted.[/dim]")
        sys.exit(130)


def _build_sfid_to_id_map(dcjson: dict) -> dict[str, str]:
    """Build a map of _SF.sfId → item id across all repeater sections."""
    result: dict[str, str] = {}
    for card_name in ("Assets", "Liabilities", "Family", "Pensions", "Protections"):
        for client in ("Client1", "Client2"):
            section = dcjson.get(card_name, {}).get(client, {})
            section_key = card_name.lower()
            if card_name == "Family":
                section_key = "family"
            items = section.get(section_key, [])
            if not isinstance(items, list):
                continue
            for item in items:
                sf = item.get("_SF", {})
                if sf and sf.get("sfId") and item.get("id"):
                    result[sf["sfId"]] = item["id"]
    # IncomeExpenses
    for client in ("Client1", "Client2"):
        ie = dcjson.get("IncomeExpenses", {}).get(client, {})
        for sec in ("income", "expenditure", "emergencyFunding", "employment"):
            for item in ie.get(sec, []):
                sf = item.get("_SF", {})
                if sf and sf.get("sfId") and item.get("id"):
                    result[sf["sfId"]] = item["id"]
    return result


def _remap_change(
    change: dict, meeting_id: str, sfid_map: dict[str, str],
) -> dict:
    """Remap a change's meetingId and dcId to match the real pulled meeting."""
    from copy import deepcopy
    c = deepcopy(change)
    c["meetingId"] = meeting_id

    # Remap dcId via _SF.sfId in formData
    form_sf = (c.get("formData") or {}).get("_SF", {})
    sf_id = form_sf.get("sfId") if form_sf else None
    if sf_id and sf_id in sfid_map:
        real_id = sfid_map[sf_id]
        old_id = c.get("dcId")
        c["dcId"] = real_id
        # Update formData.id
        if c.get("formData"):
            c["formData"]["id"] = real_id
        # Update id in path
        if old_id:
            c["path"] = [real_id if seg == old_id else seg for seg in c.get("path", [])]
            slag = c.get("slag", "")
            if old_id in slag:
                c["slag"] = slag.replace(old_id, real_id)
    return c


def _apply_changes_to_dcjson(dcjson: dict, changes: list[dict]) -> dict:
    """Apply changes to a copy of dcjson to produce currentDCJSON."""
    from copy import deepcopy
    result = deepcopy(dcjson)
    for change in changes:
        path = change.get("path", [])
        val = change.get("val")
        if len(path) < 3:
            continue

        if change.get("type") == "simple":
            card, client, field = path[0], path[1], path[2]
            card_data = result.get(card, {}).get(client)
            if card_data:
                card_data[field] = val

        elif change.get("type") == "repeater" and change.get("op") == "update":
            # path: [card, client, section, itemId, field]
            if len(path) >= 5:
                card, client, section, item_id, field = (
                    path[0], path[1], path[2], path[3], path[4],
                )
                items = result.get(card, {}).get(client, {}).get(section, [])
                for item in items:
                    if item.get("id") == item_id:
                        item[field] = val
                        break
    return result


def _run_sync_file(
    session: Session, search_term: str, changes_path: Path,
    dump: Path | None, do_verify: bool,
) -> None:
    # ── Load changes file ──────────────────────────────────────────────
    console.print(Panel(f"[bold]Loading changes from {changes_path.name}[/bold]"))
    payload = json.loads(changes_path.read_text())
    file_changes = payload["changes"]
    file_initial = payload.get("initialDCJSON", {})
    console.print(f"  Changes in file: [bold]{len(file_changes)}[/bold]")
    console.print(f"  initialDCJSON present: [bold]{bool(file_initial)}[/bold]")

    # ── Auth ──────────────────────────────────────────────────────────
    console.print(Panel("[bold]Step 0: Authentication[/bold]"))
    login_email_password(session)
    ensure_salesforce_auth(session)

    # ── Step 1: Find & Pull fresh meeting ─────────────────────────────
    console.print(Panel("[bold]Step 1: Find & Pull fresh meeting[/bold]"))
    source = find_and_pull(session, search_term)
    fresh_dcjson = source["DCJSON"]
    meeting_id = source["meetingId"]
    swift1 = source["sfAccountId"]
    swift2 = source.get("sfAccountId2") or ""
    _dump_json(dump, "01_fresh_dcjson.json", fresh_dcjson)
    console.print(f"  Meeting ID : [bold]{meeting_id}[/bold]")
    console.print(f"  Swift1     : [bold]{swift1}[/bold]")
    if swift2:
        console.print(f"  Swift2     : [bold]{swift2}[/bold]")

    # Log what the fresh meeting has
    for card in ("Assets", "Liabilities", "Pensions", "Protections", "Family"):
        section = card.lower() if card != "Family" else "family"
        items = fresh_dcjson.get(card, {}).get("Client1", {}).get(section, [])
        if items:
            console.print(f"  {card}: [bold]{len(items)}[/bold] items")
        else:
            console.print(f"  {card}: [dim]empty[/dim]")

    # Log what the file's initialDCJSON has
    if file_initial:
        console.print("\n  [bold]File initialDCJSON contents:[/bold]")
        for card in ("Assets", "Liabilities", "Pensions", "Protections", "Family"):
            section = card.lower() if card != "Family" else "family"
            items = file_initial.get(card, {}).get("Client1", {}).get(section, [])
            if items:
                console.print(f"    {card}: [bold]{len(items)}[/bold] items")
                for item in items[:3]:
                    cat = item.get("category") or item.get("liabilityType") or item.get("dependentFirstName") or "?"
                    console.print(f"      - {cat} (owner={item.get('owner')}, id={item.get('id', '?')[:8]}…)")

    # ── Step 2: Sanitize file's initialDCJSON ───────────────────────────
    console.print(Panel("[bold]Step 2: Sanitize file's initialDCJSON[/bold]"))
    sanitized, id_map = sanitize(file_initial, fresh_dcjson, return_id_map=True)
    _dump_json(dump, "02_sanitized_dcjson.json", sanitized)
    console.print(f"  IDs remapped: [bold]{len(id_map)}[/bold]")

    # Show a few id remappings
    for old_id, new_id in list(id_map.items())[:5]:
        console.print(f"    {old_id[:12]}… → {new_id[:12]}…")
    if len(id_map) > 5:
        console.print(f"    … and {len(id_map) - 5} more")

    # Check sanitized repeater items — do they still have comesFrom / _SF?
    console.print("\n  [bold]Sanitized items check:[/bold]")
    for card in ("Assets", "Liabilities", "Pensions", "Protections", "Family"):
        section = card.lower() if card != "Family" else "family"
        items = sanitized.get(card, {}).get("Client1", {}).get(section, [])
        if not items:
            continue
        sample = items[0]
        has_comes_from = "comesFrom" in sample
        has_sf = "_SF" in sample
        console.print(
            f"    {card}[0]: comesFrom={'YES [red]BAD[/red]' if has_comes_from else '[green]stripped[/green]'}"
            f"  _SF={'YES [red]BAD[/red]' if has_sf else '[green]stripped[/green]'}"
            f"  id={sample.get('id', '?')[:12]}…"
        )

    # Now look at the file's changes and what needs remapping
    console.print("\n  [bold]File changes inspection:[/bold]")
    for i, change in enumerate(file_changes):
        dc_id = change.get("dcId", "?")
        new_id = id_map.get(dc_id, "NOT FOUND")
        sf_id = (change.get("formData") or {}).get("_SF", {}).get("sfId", "?")
        console.print(
            f"    Change {i}: op={change.get('op')} field={change.get('fieldName')}"
        )
        console.print(
            f"      dcId={dc_id[:12]}… → mapped={new_id[:12] + '…' if new_id != 'NOT FOUND' else '[red]NOT FOUND[/red]'}"
        )
        console.print(f"      formData._SF.sfId={sf_id}")
        console.print(f"      formData.comesFrom={change.get('formData', {}).get('comesFrom', 'N/A')}")
        console.print(f"      path={change.get('path')}")
        console.print(f"      sObjectName={change.get('sObjectName')}")

    # ── Step 3: Generate changes ────────────────────────────────────────
    console.print(Panel("[bold]Step 3: Generate Changes (fresh vs sanitized)[/bold]"))
    creates, updates = generate_all_changes(fresh_dcjson, sanitized, meeting_id)
    console.print(
        f"  CREATE changes: [bold green]{len(creates)}[/bold green]  |  "
        f"UPDATE changes: [bold yellow]{len(updates)}[/bold yellow]"
    )
    _dump_json(dump, "03_create_changes.json", {"changes": creates})
    _dump_json(dump, "04_update_changes.json", {"changes": updates})

    create_by_card = Counter(c["path"][0] for c in creates)
    update_by_card = Counter(u["path"][0] for u in updates)
    console.print("\n  [bold]CREATEs by card:[/bold]")
    for card, count in sorted(create_by_card.items()):
        console.print(f"    {card}: {count}")
    console.print("\n  [bold]UPDATEs by card:[/bold]")
    for card, count in sorted(update_by_card.items()):
        console.print(f"    {card}: {count}")

    if not creates and not updates:
        console.print("\n[yellow]No changes generated — nothing to sync.[/yellow]")
        return

    # ── Step 4: Sync ──────────────────────────────────────────────────
    console.print(Panel("[bold]Step 4: Sync Changes[/bold]"))

    create_result = sync_create_changes(
        session, meeting_id, creates, fresh_dcjson, sanitized,
    )
    _dump_json(dump, "05_create_result.json", create_result)
    if not create_result["success"]:
        console.print(f"[bold red]CREATE sync failed:[/bold red] {create_result['message']}")
        return
    console.print(f"  [green]CREATE sync OK[/green]: {create_result['message']}")

    update_result = sync_update_changes(
        session, meeting_id, updates, fresh_dcjson, sanitized,
    )
    _dump_json(dump, "06_update_result.json", update_result)
    if not update_result["success"]:
        console.print(f"[bold red]UPDATE sync failed:[/bold red] {update_result['message']}")
        return
    console.print(f"  [green]UPDATE sync OK[/green]: {update_result['message']}")

    if not do_verify:
        return

    # ── Step 5: Verify ────────────────────────────────────────────────
    console.print(Panel("[bold]Step 5: Verify[/bold]"))
    console.print("Re-pulling meeting from Salesforce…")
    verify_pull = pull_meeting(session, swift1, swift2, meeting_id)
    verify_dcjson = transform_dcjson(verify_pull["DCJSON"])
    _dump_json(dump, "07_verify_dcjson.json", verify_dcjson)

    report = verify(sanitized, verify_dcjson)
    _dump_json(dump, "08_verification_report.json", report)
    print_report(report)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
