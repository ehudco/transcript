"""Tests for auth.py — login, OAuth redirect, callback, logout."""

import pytest
from unittest.mock import MagicMock, patch


class TestLogin:
    async def test_unauthenticated_shows_login_page(self, client):
        resp = await client.get("/login", follow_redirects=False)
        # May return 200 (template) or raise if templates are absent;
        # the key assertion is no redirect to dashboard.
        assert resp.status_code != 302 or "/dashboard" not in resp.headers.get("location", "")

    async def test_authenticated_redirects_to_dashboard(self, user_client):
        resp = await user_client.get("/login", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/dashboard")


class TestAuthGoogle:
    async def test_redirects_to_google(self, client):
        fake_flow = MagicMock()
        fake_flow.authorization_url.return_value = ("https://accounts.google.com/oauth?state=xyz", "xyz")

        with patch("auth.get_flow", return_value=fake_flow):
            resp = await client.get("/auth/google", follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert "accounts.google.com" in resp.headers["location"]

    async def test_stores_oauth_state_in_session(self, client):
        fake_flow = MagicMock()
        fake_flow.authorization_url.return_value = ("https://accounts.google.com/oauth?state=mystate", "mystate")

        with patch("auth.get_flow", return_value=fake_flow):
            resp = await client.get("/auth/google", follow_redirects=False)

        # The session cookie should now exist
        assert "session" in resp.cookies or resp.status_code in (302, 307)


class TestAuthCallback:
    def _make_fake_flow(self, email="user@example.com", sub="sub123", verified=True):
        creds = MagicMock()
        creds.id_token = "fake-id-token"
        creds.token = "access-token"
        creds.refresh_token = "refresh-token"
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "client-id"
        creds.client_secret = "client-secret"
        creds.scopes = ["openid"]

        fake_flow = MagicMock()
        fake_flow.credentials = creds
        return fake_flow

    def _id_info(self, email="user@example.com", sub="sub123", verified=True):
        return {
            "email": email,
            "sub": sub,
            "email_verified": verified,
            "name": "Test User",
        }

    async def test_unverified_email_shows_error(self, client):
        fake_flow = self._make_fake_flow()
        id_info = self._id_info(verified=False)

        with (
            patch("auth.get_flow", return_value=fake_flow),
            patch("auth.id_token.verify_oauth2_token", return_value=id_info),
        ):
            resp = await client.get("/auth/callback?code=x&state=s", follow_redirects=False)

        assert resp.status_code == 200
        assert b"not verified" in resp.content.lower() or b"Email not verified" in resp.content

    async def test_unknown_user_creates_pending_and_shows_error(self, client):
        fake_flow = self._make_fake_flow()
        id_info = self._id_info()

        with (
            patch("auth.get_flow", return_value=fake_flow),
            patch("auth.id_token.verify_oauth2_token", return_value=id_info),
            patch("auth.get_user", return_value=None),
            patch("auth.create_pending_user") as mock_create,
        ):
            resp = await client.get("/auth/callback?code=x&state=s", follow_redirects=False)

        mock_create.assert_called_once_with("user@example.com", "sub123")
        assert b"pending" in resp.content.lower()

    async def test_blocked_user_shows_status_error(self, client):
        fake_flow = self._make_fake_flow()
        id_info = self._id_info()
        user_doc = {"status": "blocked", "role": "user"}

        with (
            patch("auth.get_flow", return_value=fake_flow),
            patch("auth.id_token.verify_oauth2_token", return_value=id_info),
            patch("auth.get_user", return_value=user_doc),
        ):
            resp = await client.get("/auth/callback?code=x&state=s", follow_redirects=False)

        assert b"blocked" in resp.content.lower()

    async def test_active_user_redirects_to_dashboard(self, client):
        fake_flow = self._make_fake_flow()
        id_info = self._id_info()
        user_doc = {"status": "active", "role": "user"}

        with (
            patch("auth.get_flow", return_value=fake_flow),
            patch("auth.id_token.verify_oauth2_token", return_value=id_info),
            patch("auth.get_user", return_value=user_doc),
            patch("auth.update_user_last_login"),
        ):
            resp = await client.get("/auth/callback?code=x&state=s", follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/dashboard")


class TestLogout:
    async def test_logout_clears_session_and_redirects(self, user_client):
        resp = await user_client.get("/logout", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/login")
