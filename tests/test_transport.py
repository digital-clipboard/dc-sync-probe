"""Tests for transport.py — HTTP/GraphQL transport layer."""

import json
from unittest.mock import MagicMock, patch

import pytest

from dc_sync_probe.config import Session
from dc_sync_probe.transport import (
    GraphQLError,
    SessionExpiredError,
    TransportError,
    _check_session_expired,
    graphql,
    post_json,
)


class TestCheckSessionExpired:
    def test_401_raises(self):
        with pytest.raises(SessionExpiredError, match="HTTP 401"):
            _check_session_expired(401, None)

    def test_err_message_invalid_signature(self):
        body = {"err": {"message": "invalid signature detected"}}
        with pytest.raises(SessionExpiredError, match="Session expired"):
            _check_session_expired(200, body)

    def test_message_token_timeout(self):
        body = {"message": "token_session_timeout"}
        with pytest.raises(SessionExpiredError):
            _check_session_expired(200, body)

    def test_error_name_jwtautherror(self):
        body = {"error": {"name": "JwtAuthError"}}
        with pytest.raises(SessionExpiredError):
            _check_session_expired(200, body)

    def test_normal_response_ok(self):
        _check_session_expired(200, {"data": {"result": "ok"}})

    def test_none_body_ok(self):
        _check_session_expired(200, None)


class TestGraphQLError:
    def test_stores_errors(self):
        errors = [{"message": "Field not found"}]
        exc = GraphQLError(errors)
        assert exc.errors == errors
        assert "Field not found" in str(exc)


class TestExceptionHierarchy:
    def test_session_expired_is_transport_error(self):
        assert issubclass(SessionExpiredError, TransportError)

    def test_graphql_error_is_transport_error(self):
        assert issubclass(GraphQLError, TransportError)


class TestGraphQL:
    @patch("dc_sync_probe.transport.httpx.Client")
    def test_successful_query(self, mock_client_cls):
        session = Session("dev")
        session.token = "test-token"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"data":{"search":{"data":"[]"}}}'
        mock_resp.json.return_value = {"data": {"search": {"data": "[]"}}}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = graphql(session, "query { search { data } }")
        assert result == {"search": {"data": "[]"}}

    @patch("dc_sync_probe.transport.httpx.Client")
    def test_graphql_errors_raise(self, mock_client_cls):
        session = Session("dev")
        session.token = "tok"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"errors":[{"message":"bad"}]}'
        mock_resp.json.return_value = {"errors": [{"message": "bad"}]}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(GraphQLError, match="bad"):
            graphql(session, "query { broken }")

    @patch("dc_sync_probe.transport.httpx.Client")
    def test_session_expired_on_401(self, mock_client_cls):
        session = Session("dev")
        session.token = "expired"

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.content = b'{}'
        mock_resp.json.return_value = {}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(SessionExpiredError):
            graphql(session, "query { x }")


class TestPostJson:
    @patch("dc_sync_probe.transport.httpx.Client")
    def test_successful_post(self, mock_client_cls):
        session = Session("dev")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"token":"jwt123"}'
        mock_resp.json.return_value = {"token": "jwt123"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = post_json(session, "https://example.com/signin", {"email": "a", "password": "b"})
        assert result == {"token": "jwt123"}
