"""
Integration tests for the Picker API key — make real HTTP calls to Google.

Run with GCP credentials (Cloud Shell / VM):
    GOOGLE_CLOUD_PROJECT=whisper-project-462317 python -m pytest tests/test_picker_key_integration.py -v -s

Run without GCP credentials (local PC) by passing the key directly:
    PICKER_API_KEY=AIzaSy... python -m pytest tests/test_picker_key_integration.py -v -s

Skipped automatically when neither GOOGLE_CLOUD_PROJECT nor PICKER_API_KEY is set.
"""

import os
import pytest
import httpx

pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_CLOUD_PROJECT") and not os.environ.get("PICKER_API_KEY"),
    reason="Set PICKER_API_KEY=<key> or GOOGLE_CLOUD_PROJECT=<project> to run integration tests"
)


@pytest.fixture(scope="module")
def picker_api_key():
    """Read from env var directly, or fall back to Secret Manager."""
    key = os.environ.get("PICKER_API_KEY")
    if not key:
        from secret_client import get_secret
        key = get_secret("PICKER_API_KEY")
    key = key.strip()
    assert key, "PICKER_API_KEY is empty"
    return key


class TestPickerApiKeyAgainstGoogle:

    def test_key_is_not_empty(self, picker_api_key):
        assert len(picker_api_key) > 10

    def test_key_has_no_whitespace_or_newlines(self, picker_api_key):
        assert picker_api_key == picker_api_key.strip(), \
            "Key has leading/trailing whitespace or newlines"
        assert "\n" not in picker_api_key, "Key contains newline"
        assert " " not in picker_api_key, "Key contains space"

    def test_key_accepted_by_google_drive_api(self, picker_api_key):
        """
        A valid API key gets a 401 (needs OAuth) from the Drive API.
        An invalid key gets a 400 with 'API key not valid'.
        """
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params={"key": picker_api_key},
            timeout=10,
        )
        # 401 = key is valid, just needs OAuth token (expected)
        # 400 = key is invalid
        # 403 = key is valid but API not enabled or referrer blocked
        assert resp.status_code != 400, (
            f"Google rejected the key as invalid. Response: {resp.text}"
        )
        if resp.status_code == 403:
            error = resp.json().get("error", {})
            errors = error.get("errors", [{}])
            reason = errors[0].get("reason", "")
            assert reason != "keyInvalid", (
                f"Key is invalid according to Google: {resp.text}"
            )
            # 403 with a different reason (e.g. referrerNotAllowed or
            # accessNotConfigured) means the key itself is fine
            pytest.skip(f"Key is valid but blocked by restriction: {reason}")

        assert resp.status_code == 401, (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )

    def test_key_not_blocked_by_referrer_restriction(self, picker_api_key):
        """
        Server-side requests have no HTTP Referer header.
        If the key has HTTP referrer restrictions, this call will get a 403
        with reason 'refererNotAllowed' — meaning the key WILL work from
        a browser on the right domain but NOT from the server.
        This test documents which case you are in.
        """
        resp = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            params={"key": picker_api_key},
            timeout=10,
        )
        if resp.status_code == 403:
            errors = resp.json().get("error", {}).get("errors", [{}])
            reason = errors[0].get("reason", "")
            if reason == "refererNotAllowed":
                pytest.skip(
                    "Key has HTTP referrer restrictions — it will work from "
                    "the browser but not server-side. This is expected if you "
                    "restricted the key to your Cloud Run domain."
                )
            elif reason == "accessNotConfigured":
                pytest.fail(
                    "Drive API is not enabled for this project/key. "
                    "Enable it at: GCP Console → APIs & Services → Library → Google Drive API"
                )
