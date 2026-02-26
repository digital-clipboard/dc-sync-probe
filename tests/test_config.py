"""Tests for config.py — Session class and environment configuration."""

import pytest

from dc_sync_probe.config import ENVIRONMENTS, Session


class TestEnvironments:
    def test_all_envs_have_required_keys(self):
        for name, env in ENVIRONMENTS.items():
            assert "api_url" in env, f"{name} missing api_url"
            assert "graphql_url" in env, f"{name} missing graphql_url"

    def test_graphql_url_ends_with_graphql(self):
        for name, env in ENVIRONMENTS.items():
            assert env["graphql_url"].endswith("/graphql"), f"{name} graphql_url incorrect"


class TestSession:
    def test_valid_env(self):
        s = Session("dev")
        assert s.api_url == ENVIRONMENTS["dev"]["api_url"]
        assert s.graphql_url == ENVIRONMENTS["dev"]["graphql_url"]
        assert s.token is None

    def test_env_case_insensitive(self):
        s = Session("DEV")
        assert s.api_url == ENVIRONMENTS["dev"]["api_url"]

    def test_invalid_env_raises(self):
        with pytest.raises(ValueError, match="Unknown environment"):
            Session("nonexistent")

    def test_headers_without_token(self):
        s = Session("dev")
        h = s.headers
        assert h["Content-Type"] == "application/json"
        assert "Authorization" not in h

    def test_headers_with_token(self):
        s = Session("dev")
        s.token = "my-jwt-token"
        h = s.headers
        assert h["Authorization"] == "Bearer my-jwt-token"

    def test_is_authenticated(self):
        s = Session("dev")
        assert not s.is_authenticated
        s.token = "tok"
        assert s.is_authenticated
