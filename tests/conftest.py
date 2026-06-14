"""
Shared fixtures for the test suite.

All Google Cloud clients (Firestore, Secret Manager, Compute, Pub/Sub) and
the Google OAuth flow are patched so no real credentials are required.
"""

import base64
import importlib
import json
import sys
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner

SECRET_KEY = "test-session-secret-32-chars-long!!"

SECRETS = {
    "SESSION_SECRET": SECRET_KEY,
    "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
}


def _fake_get_secret(name: str) -> str:
    return SECRETS.get(name, f"fake-{name}")


def make_session_cookie(data: dict) -> str:
    """Produce a signed starlette session cookie value from *data*."""
    signer = TimestampSigner(SECRET_KEY)
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    return signer.sign(payload).decode()


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def mock_firestore_db():
    """A MagicMock that acts as a Firestore db client."""
    return MagicMock()


@pytest.fixture(scope="function")
def patched_app(mock_firestore_db):
    """
    Returns a FastAPI app with all GCP calls mocked out.
    Modules are reloaded so patches are applied cleanly for every test.
    """
    # Remove cached module state so reloads are clean
    for mod in ["main", "auth", "admin", "jobs", "firestore_client", "secret_client", "compute"]:
        sys.modules.pop(mod, None)

    with (
        patch("google.cloud.firestore.Client", return_value=mock_firestore_db),
        patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=MagicMock()),
        patch("secret_client.get_secret", side_effect=_fake_get_secret),
        patch("google.auth.default", return_value=(MagicMock(), "test-project")),
        patch("googleapiclient.discovery.build", return_value=MagicMock()),
    ):
        import main as main_module  # noqa: PLC0415
        yield main_module.app

    # Clean up again after the test
    for mod in ["main", "auth", "admin", "jobs", "firestore_client", "secret_client", "compute"]:
        sys.modules.pop(mod, None)


@pytest_asyncio.fixture()
async def client(patched_app) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated async HTTP client."""
    async with AsyncClient(
        transport=ASGITransport(app=patched_app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture()
async def user_client(patched_app) -> AsyncGenerator[AsyncClient, None]:
    """Client with a regular-user session cookie pre-set."""
    session_data = {
        "user": {"email": "user@example.com", "sub": "sub123", "role": "user", "name": "Test User"},
        "oauth_tokens": {"token": "tok", "refresh_token": "ref", "token_uri": "uri",
                         "client_id": "cid", "client_secret": "csec", "scopes": []},
    }
    cookie = make_session_cookie(session_data)
    async with AsyncClient(
        transport=ASGITransport(app=patched_app),
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as ac:
        yield ac


@pytest_asyncio.fixture()
async def admin_client(patched_app) -> AsyncGenerator[AsyncClient, None]:
    """Client with an admin session cookie pre-set."""
    session_data = {
        "user": {"email": "admin@example.com", "sub": "admsub", "role": "admin", "name": "Admin User"},
    }
    cookie = make_session_cookie(session_data)
    async with AsyncClient(
        transport=ASGITransport(app=patched_app),
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as ac:
        yield ac
