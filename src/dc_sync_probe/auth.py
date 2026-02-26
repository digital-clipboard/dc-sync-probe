"""Authentication helpers: email/password login and Salesforce SSO."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from .config import Session
from .transport import graphql, post_json

console = Console()

_CONFIG_FILE = Path("config.local.json")


def _load_credentials() -> tuple[str | None, str | None]:
    """Load email/password from config.local.json if it exists."""
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text())
            return data.get("email"), data.get("password")
        except (json.JSONDecodeError, KeyError):
            pass
    return None, None


def login_email_password(session: Session) -> None:
    """Authenticate via email + password (POST /signin)."""
    email, password = _load_credentials()
    if email and password:
        console.print(f"[dim]Using credentials from {_CONFIG_FILE}[/dim]")
    else:
        email = Prompt.ask("[bold]Email[/bold]")
        password = Prompt.ask("[bold]Password[/bold]", password=True)

    url = f"{session.api_url}/signin"
    data = post_json(session, url, {"email": email, "password": password})

    token = data.get("token")
    if not token:
        raise RuntimeError(f"Login failed: {data}")

    session.token = token
    console.print("[green]Logged in successfully.[/green]")


# -- Salesforce SSO -----------------------------------------------------

def _is_sf_authenticated(session: Session) -> bool:
    query = "query { isUserAuthenticatedWithSalesforce { success message } }"
    data = graphql(session, query)
    result = data.get("isUserAuthenticatedWithSalesforce", {})
    return bool(result.get("success"))


def _get_sf_auth_url(session: Session) -> str:
    data = graphql(
        session,
        "query { getAuthorizationUrl { success url } }",
    )
    result = data.get("getAuthorizationUrl", {})
    if not result.get("success") or not result.get("url"):
        raise RuntimeError(f"Failed to get SF auth URL: {result}")
    return result["url"]


def _exchange_sf_code(session: Session, code: str) -> None:
    data = graphql(
        session,
        'mutation($code: String!) { authenticateSalesforceWithSSO(code: $code) { success message } }',
        variables={"code": code},
    )
    result = data.get("authenticateSalesforceWithSSO", {})
    if not result.get("success"):
        raise RuntimeError(f"SF SSO exchange failed: {result.get('message')}")


def ensure_salesforce_auth(session: Session) -> None:
    """Make sure the current session is also authenticated with Salesforce.

    If not, guide the user through the OAuth flow.
    """
    if _is_sf_authenticated(session):
        console.print("[dim]Salesforce session already active.[/dim]")
        return

    auth_url = _get_sf_auth_url(session)
    console.print(f"\n[bold]Open this URL to authenticate with Salesforce:[/bold]\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = Prompt.ask("[bold]Paste the authorization code from the redirect URL[/bold]")
    _exchange_sf_code(session, code.strip())
    console.print("[green]Salesforce authentication complete.[/green]")
