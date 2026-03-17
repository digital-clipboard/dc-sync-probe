"""Backend environment configuration and auth header management."""

from __future__ import annotations

_ENV_DEFS: dict[str, dict[str, str]] = {
    "local": {
        "api_url": "http://localhost:3000",
        "graphql_url": "http://localhost:3000/graphql",
    },
    "dev": {
        "api_url": "https://backend.dev.sjp.digitalclipboard.com",
        "graphql_url": "https://backend.dev.sjp.digitalclipboard.com/graphql",
    },
    "uat": {
        "api_url": "https://backend.uat.sjp.digitalclipboard.com",
        "graphql_url": "https://backend.uat.sjp.digitalclipboard.com/graphql",
    },
    "dc-prod": {
        "api_url": "https://backend.digitalclipboard.com",
        "graphql_url": "https://backend.digitalclipboard.com/graphql",
    },
    "sjp-uat": {
        "api_url": "https://nlb-dcservicesuat.sjp.co.uk",
        "graphql_url": "https://nlb-dcservicesuat.sjp.co.uk/graphql",
    },
    "sjp-prod": {
        "api_url": "https://nlb-dcservices.sjp.co.uk",
        "graphql_url": "https://nlb-dcservices.sjp.co.uk/graphql",
    },
}

# Aliases for backward compatibility
ENVIRONMENTS: dict[str, dict[str, str]] = {
    **_ENV_DEFS,
    "feature": _ENV_DEFS["dev"],
    "staging": _ENV_DEFS["uat"],
    "dc_prod": _ENV_DEFS["dc-prod"],
    "sjp_uat": _ENV_DEFS["sjp-uat"],
    "sjp_prod": _ENV_DEFS["sjp-prod"],
}

DEFAULT_TIMEOUT = 45.0  # seconds


class Session:
    """Holds auth token and environment config for the lifetime of a run."""

    def __init__(self, env_name: str) -> None:
        env_name = env_name.lower()
        if env_name not in ENVIRONMENTS:
            raise ValueError(
                f"Unknown environment {env_name!r}. "
                f"Choose from: {', '.join(ENVIRONMENTS)}"
            )
        env = ENVIRONMENTS[env_name]
        self.api_url: str = env["api_url"]
        self.graphql_url: str = env["graphql_url"]
        self.token: str | None = None

    # -- helpers --------------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    @property
    def is_authenticated(self) -> bool:
        return self.token is not None
