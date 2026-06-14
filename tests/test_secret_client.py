"""Tests for secret_client.py — get_secret."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _clean_module():
    import sys
    sys.modules.pop("secret_client", None)
    yield
    sys.modules.pop("secret_client", None)


class TestGetSecret:
    def test_returns_decoded_payload(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value.payload.data = b"my-secret-value"

        with patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client):
            import secret_client
            result = secret_client.get_secret("MY_SECRET")

        assert result == "my-secret-value"

    def test_builds_correct_secret_name(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value.payload.data = b"value"

        with (
            patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client),
            patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "my-project"}),
        ):
            import secret_client
            secret_client.get_secret("SOME_KEY")

        call_args = mock_client.access_secret_version.call_args
        name = call_args.kwargs["request"]["name"]
        assert name == "projects/my-project/secrets/SOME_KEY/versions/latest"

    def test_uses_env_project_id(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value.payload.data = b"v"

        with (
            patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client),
            patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "custom-project-id"}),
        ):
            import secret_client
            secret_client.get_secret("KEY")

        name = mock_client.access_secret_version.call_args.kwargs["request"]["name"]
        assert "custom-project-id" in name

    def test_falls_back_to_default_project(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value.payload.data = b"v"

        import os
        env_without_project = {k: v for k, v in os.environ.items() if k != "GOOGLE_CLOUD_PROJECT"}
        with (
            patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client),
            patch.dict("os.environ", env_without_project, clear=True),
        ):
            import secret_client
            secret_client.get_secret("KEY")

        name = mock_client.access_secret_version.call_args.kwargs["request"]["name"]
        assert "whisper-project-462317" in name
