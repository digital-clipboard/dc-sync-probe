"""Authentication helpers: email/password login and Salesforce SSO."""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rich.console import Console
from rich.prompt import Prompt

from .config import Session
from .transport import graphql, post_json

console = Console()

_CONFIG_FILE = Path("config.local.json")

# The redirect URI registered in Salesforce (premeet-advisor frontend)
_OAUTH_REDIRECT_HOST = "localhost"
_OAUTH_REDIRECT_PORT = 3001
_OAUTH_REDIRECT_PATH = "/oauth/salesforce"


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


def _is_port_available(port: int) -> bool:
    """Check if a port is available to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _capture_oauth_code_via_server() -> str | None:
    """Start a temporary HTTP server to capture the OAuth redirect code.

    Returns the authorization code, or None if the server could not start.
    """
    captured_code: list[str] = []
    server_ready = threading.Event()

    class OAuthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == _OAUTH_REDIRECT_PATH:
                params = parse_qs(parsed.query)
                code_list = params.get("code", [])
                if code_list:
                    captured_code.append(code_list[0])

                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Salesforce authentication captured!</h2>"
                    b"<p>You can close this tab and return to the CLI.</p>"
                    b"</body></html>"
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress HTTP logs

    if not _is_port_available(_OAUTH_REDIRECT_PORT):
        return None

    server = HTTPServer(
        (_OAUTH_REDIRECT_HOST, _OAUTH_REDIRECT_PORT), OAuthHandler,
    )
    server.timeout = 120  # 2 minute timeout

    def _serve():
        server_ready.set()
        while not captured_code:
            server.handle_request()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    server_ready.wait()

    # Wait for code (up to 120 seconds)
    deadline = time.monotonic() + 120
    while not captured_code and time.monotonic() < deadline:
        time.sleep(0.5)

    try:
        server.server_close()
    except Exception:
        pass

    return captured_code[0] if captured_code else None


def _poll_sf_auth(session: Session, timeout: int = 120) -> bool:
    """Poll isUserAuthenticatedWithSalesforce until success or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_sf_authenticated(session):
            return True
        time.sleep(3)
    return False


def ensure_salesforce_auth(session: Session) -> None:
    """Make sure the current session is also authenticated with Salesforce.

    Strategy:
    1. If already authenticated, return immediately.
    2. Try to start a local server on port 3001 to capture the OAuth code.
    3. If port 3001 is taken (premeet-advisor running), open the browser
       and poll until the user completes auth in the web app.
    """
    if _is_sf_authenticated(session):
        console.print("[dim]Salesforce session already active.[/dim]")
        return

    auth_url = _get_sf_auth_url(session)

    if _is_port_available(_OAUTH_REDIRECT_PORT):
        # Strategy A: capture code via local server
        console.print("[dim]Starting local OAuth server on port 3001...[/dim]")
        console.print("[bold]Opening browser for Salesforce login...[/bold]")
        webbrowser.open(auth_url)

        code = _capture_oauth_code_via_server()
        if code:
            _exchange_sf_code(session, code)
            console.print("[green]Salesforce authentication complete.[/green]")
            return
        else:
            console.print("[yellow]OAuth capture timed out.[/yellow]")
            raise RuntimeError("Salesforce OAuth timed out. Try again.")
    else:
        # Strategy B: premeet-advisor is running on 3001 — let user complete there
        console.print(
            "[bold]Port 3001 is in use (premeet-advisor?).[/bold]\n"
            "Opening browser for Salesforce login — complete it in the web app."
        )
        webbrowser.open(auth_url)
        Prompt.ask(
            "\n[bold]Press Enter once you've completed the Salesforce login in your browser[/bold]"
        )

        if _is_sf_authenticated(session):
            console.print("[green]Salesforce authentication complete.[/green]")
        else:
            raise RuntimeError(
                "Salesforce auth not detected. "
                "Please complete SF login in premeet-advisor and retry."
            )
