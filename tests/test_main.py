"""Tests for main.py — root and dashboard routes."""

import pytest
from unittest.mock import patch


class TestRoot:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/login")

    async def test_authenticated_redirects_to_dashboard(self, user_client):
        resp = await user_client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/dashboard")


class TestDashboard:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/login")

    async def test_authenticated_returns_200(self, user_client):
        with patch("main.get_secret", side_effect=lambda k: f"fake-{k}"):
            resp = await user_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200

    async def test_picker_api_key_rendered_in_page(self, user_client):
        """API_KEY must appear in the dashboard HTML so the Picker can load."""
        with patch("main.get_secret", side_effect=lambda k: f"fake-{k}"):
            resp = await user_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200
        assert b"fake-PICKER_API_KEY" in resp.content

    async def test_google_client_id_rendered_in_page(self, user_client):
        """CLIENT_ID must appear in the dashboard HTML."""
        with patch("main.get_secret", side_effect=lambda k: f"fake-{k}"):
            resp = await user_client.get("/dashboard", follow_redirects=False)
        assert b"fake-GOOGLE_CLIENT_ID" in resp.content

    async def test_oauth_token_rendered_in_page(self, user_client):
        """OAUTH_TOKEN must be non-empty so the Picker can authenticate."""
        with patch("main.get_secret", side_effect=lambda k: f"fake-{k}"):
            resp = await user_client.get("/dashboard", follow_redirects=False)
        # The user_client fixture sets oauth_tokens with token="tok"
        assert b'"tok"' in resp.content or b"tok" in resp.content

    async def test_missing_secret_raises_rather_than_silently_empty(self, user_client):
        """If get_secret fails, the dashboard must NOT render a 200 with an empty API key."""
        with patch("main.get_secret", side_effect=Exception("Secret not found")):
            with pytest.raises(Exception, match="Secret not found"):
                await user_client.get("/dashboard", follow_redirects=False)


class TestPickerApiKeyValidity:
    """
    Replicate the 'The API developer key is invalid' error from Google Picker.
    The key reaches the browser invalid when it is empty, whitespace-only,
    or has a trailing newline — all common with Secret Manager copy-paste.
    """

    async def _get_dashboard(self, user_client, key_value):
        with patch("main.get_secret", side_effect=lambda k:
                   key_value if k == "PICKER_API_KEY" else f"fake-{k}"):
            return await user_client.get("/dashboard", follow_redirects=False)

    async def test_valid_key_renders_clean(self, user_client):
        resp = await self._get_dashboard(user_client, "AIzaSyABCDEF1234567890")
        assert resp.status_code == 200
        assert b"AIzaSyABCDEF1234567890" in resp.content
        # Must not have surrounding whitespace in the JS string
        assert b'"AIzaSyABCDEF1234567890"' in resp.content

    async def test_key_with_trailing_newline_is_stripped(self, user_client):
        """Secret Manager often stores values with a trailing \\n — must be stripped."""
        resp = await self._get_dashboard(user_client, "AIzaSyABCDEF1234567890\n")
        assert resp.status_code == 200
        # Newline must NOT appear inside the JS string
        assert b"AIzaSyABCDEF1234567890\\n" not in resp.content
        assert b"AIzaSyABCDEF1234567890\n" not in resp.content
        assert b"AIzaSyABCDEF1234567890" in resp.content

    async def test_key_with_trailing_whitespace_is_stripped(self, user_client):
        """Spaces around the key cause an invalid key error."""
        resp = await self._get_dashboard(user_client, "  AIzaSyABCDEF1234567890  ")
        assert resp.status_code == 200
        assert b"AIzaSyABCDEF1234567890" in resp.content
        assert b"  AIzaSyABCDEF1234567890  " not in resp.content

    async def test_empty_key_raises_error(self, user_client):
        """An empty key must raise immediately, not render a broken page."""
        with pytest.raises(Exception, match="empty"):
            await self._get_dashboard(user_client, "")

    async def test_whitespace_only_key_raises_error(self, user_client):
        """A whitespace-only key must raise immediately, not render a broken page."""
        with pytest.raises(Exception, match="empty"):
            await self._get_dashboard(user_client, "   \n  ")
