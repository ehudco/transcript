"""
Tests for the drive.file scope server-side access flow.

With drive.file scope the Google Picker only grants client-side (JS) access.
Two things must work for the worker to access the file server-side:
  1. jobs.py calls _touch_drive_file at submit time — registers the file under
     the app's credentials on Google's side.
  2. worker.py always refreshes the access token before calling Drive API —
     because drive.file returns 404 (not 401) for expired tokens, so the
     google client library won't auto-refresh.
"""

import base64
import json
import sys
import pytest
from unittest.mock import patch, MagicMock
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner

_SECRET_KEY = "test-session-secret-32-chars-long!!"

SAMPLE_TOKENS = {
    "token": "old-access-tok",
    "refresh_token": "refresh-tok",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "client-id",
    "client_secret": "client-secret",
    "scopes": ["https://www.googleapis.com/auth/drive.file"],
}


def _make_cookie(session_data: dict) -> str:
    signer = TimestampSigner(_SECRET_KEY)
    payload = base64.b64encode(json.dumps(session_data).encode()).decode()
    return signer.sign(payload).decode()


# ---------------------------------------------------------------------------
# _touch_drive_file — unit tests
# ---------------------------------------------------------------------------

class TestTouchDriveFileUnit:
    """
    _touch_drive_file makes a server-side files.get call so Google registers
    the file as 'opened by the app' under drive.file scope.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        with (
            patch("google.cloud.firestore.Client", return_value=MagicMock()),
            patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=MagicMock()),
            patch("google.auth.default", return_value=(MagicMock(), "test-project")),
            patch("googleapiclient.discovery.build", return_value=MagicMock()),
        ):
            import jobs
            self.jobs = jobs
            yield

    def test_calls_drive_files_get_with_correct_file_id(self):
        mock_svc = MagicMock()
        with (
            patch("google.oauth2.credentials.Credentials"),
            patch("googleapiclient.discovery.build", return_value=mock_svc),
        ):
            self.jobs._touch_drive_file(SAMPLE_TOKENS, "FILE123")

        mock_svc.files().get.assert_called_with(fileId="FILE123", fields="id,name")
        mock_svc.files().get().execute.assert_called_once()

    def test_propagates_drive_exception(self):
        mock_svc = MagicMock()
        mock_svc.files().get().execute.side_effect = Exception("Drive API error")
        with (
            patch("google.oauth2.credentials.Credentials"),
            patch("googleapiclient.discovery.build", return_value=mock_svc),
        ):
            with pytest.raises(Exception, match="Drive API error"):
                self.jobs._touch_drive_file(SAMPLE_TOKENS, "FILE123")

    def test_constructs_credentials_from_all_token_fields(self):
        mock_creds_cls = MagicMock()
        mock_svc = MagicMock()
        with (
            patch("google.oauth2.credentials.Credentials", mock_creds_cls),
            patch("googleapiclient.discovery.build", return_value=mock_svc),
        ):
            self.jobs._touch_drive_file(SAMPLE_TOKENS, "FILE123")

        mock_creds_cls.assert_called_once_with(
            token=SAMPLE_TOKENS["token"],
            refresh_token=SAMPLE_TOKENS.get("refresh_token"),
            token_uri=SAMPLE_TOKENS["token_uri"],
            client_id=SAMPLE_TOKENS["client_id"],
            client_secret=SAMPLE_TOKENS["client_secret"],
            scopes=SAMPLE_TOKENS.get("scopes"),
        )

    def test_builds_drive_v3_service(self):
        mock_svc = MagicMock()
        with (
            patch("google.oauth2.credentials.Credentials") as mock_creds_cls,
            patch("googleapiclient.discovery.build", return_value=mock_svc) as mock_build,
        ):
            self.jobs._touch_drive_file(SAMPLE_TOKENS, "FILE123")

        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds_cls())


# ---------------------------------------------------------------------------
# submit endpoint — _touch_drive_file called/skipped at the right times
# ---------------------------------------------------------------------------

class TestSubmitTouchBehavior:
    async def test_touch_called_with_correct_file_id_and_tokens(self, user_client):
        with (
            patch("jobs.create_job"),
            patch("jobs.TEST_MODE", False),
            patch("jobs._touch_drive_file") as mock_touch,
            patch("compute.get_vm_status", return_value="RUNNING"),
        ):
            await user_client.post(
                "/submit",
                data={"file_id": "FILE123", "file_name": "audio.mp4"},
                follow_redirects=False,
            )

        mock_touch.assert_called_once()
        called_tokens, called_file_id = mock_touch.call_args[0]
        assert called_file_id == "FILE123"
        assert called_tokens["token"] == "tok"  # from user_client fixture

    async def test_touch_not_called_in_test_mode(self, user_client):
        with (
            patch("jobs.create_job"),
            patch("jobs.TEST_MODE", True),
            patch("jobs._touch_drive_file") as mock_touch,
        ):
            await user_client.post(
                "/submit",
                data={"file_id": "FILE123", "file_name": "audio.mp4"},
                follow_redirects=False,
            )

        mock_touch.assert_not_called()

    async def test_touch_failure_does_not_cause_500(self, user_client):
        """Touch failure is logged as a warning — it must not block job submission."""
        with (
            patch("jobs.create_job"),
            patch("jobs.TEST_MODE", False),
            patch("jobs._touch_drive_file", side_effect=Exception("Drive unavailable")),
            patch("compute.get_vm_status", return_value="RUNNING"),
        ):
            resp = await user_client.post(
                "/submit",
                data={"file_id": "FILE123", "file_name": "audio.mp4"},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 303, 307)
        assert "/job/" in resp.headers["location"]

    async def test_touch_not_called_when_session_has_no_tokens(self, patched_app):
        """If the session has no oauth_tokens, _touch_drive_file must be skipped."""
        session_data = {
            "user": {
                "email": "user@example.com", "sub": "sub123",
                "role": "user", "name": "Test User",
            },
            # no oauth_tokens key
        }
        cookie = _make_cookie(session_data)
        async with AsyncClient(
            transport=ASGITransport(app=patched_app),
            base_url="http://testserver",
            cookies={"session": cookie},
        ) as ac:
            with (
                patch("jobs.create_job"),
                patch("jobs.TEST_MODE", False),
                patch("jobs._touch_drive_file") as mock_touch,
                patch("compute.get_vm_status", return_value="RUNNING"),
            ):
                await ac.post(
                    "/submit",
                    data={"file_id": "FILE123", "file_name": "audio.mp4"},
                    follow_redirects=False,
                )

        mock_touch.assert_not_called()


# ---------------------------------------------------------------------------
# worker build_drive_service — explicit token refresh
# ---------------------------------------------------------------------------

class TestBuildDriveServiceRefresh:
    """
    drive.file scope returns 404 (not 401) for expired tokens, so the google
    client library never auto-refreshes. worker.py must call creds.refresh()
    explicitly when a refresh_token is present.
    """

    @pytest.fixture(autouse=True)
    def _clean(self):
        sys.modules.pop("worker", None)
        yield
        sys.modules.pop("worker", None)

    @pytest.fixture()
    def worker(self):
        with (
            patch("google.cloud.firestore.Client", return_value=MagicMock()),
            patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=MagicMock()),
            patch("secret_client.get_secret", return_value="fake"),
            patch("google.auth.default", return_value=(MagicMock(), "proj")),
            patch("googleapiclient.discovery.build", return_value=MagicMock()),
        ):
            import worker as w
            yield w

    def test_refresh_called_when_refresh_token_present(self, worker):
        mock_creds = MagicMock()
        mock_creds.refresh_token = "refresh-tok"
        with (
            patch("worker.Credentials", return_value=mock_creds),
            patch("worker.build", return_value=MagicMock()),
            patch("worker.GoogleAuthRequest"),
        ):
            worker.build_drive_service(SAMPLE_TOKENS)

        mock_creds.refresh.assert_called_once()

    def test_refresh_not_called_when_no_refresh_token(self, worker):
        """No refresh_token means we can't refresh — use stale token and accept it may fail."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = None
        tokens_no_refresh = {**SAMPLE_TOKENS, "refresh_token": None}
        with (
            patch("worker.Credentials", return_value=mock_creds),
            patch("worker.build", return_value=MagicMock()),
        ):
            worker.build_drive_service(tokens_no_refresh)

        mock_creds.refresh.assert_not_called()

    def test_refresh_failure_raises_and_does_not_silently_use_stale_token(self, worker):
        """Silently proceeding with a stale token causes a confusing 404 — raise instead."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = "refresh-tok"
        mock_creds.refresh.side_effect = Exception("invalid_grant")
        with (
            patch("worker.Credentials", return_value=mock_creds),
            patch("worker.build", return_value=MagicMock()),
            patch("worker.GoogleAuthRequest"),
        ):
            with pytest.raises(Exception, match="invalid_grant"):
                worker.build_drive_service(SAMPLE_TOKENS)

    def test_builds_drive_v3_with_the_refreshed_credentials(self, worker):
        mock_creds = MagicMock()
        mock_creds.refresh_token = "refresh-tok"
        with (
            patch("worker.Credentials", return_value=mock_creds),
            patch("worker.build") as mock_build,
            patch("worker.GoogleAuthRequest"),
        ):
            worker.build_drive_service(SAMPLE_TOKENS)

        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)


# ---------------------------------------------------------------------------
# worker process_job — Drive error handling
# ---------------------------------------------------------------------------

class TestProcessJobDriveErrors:
    @pytest.fixture(autouse=True)
    def _clean(self):
        sys.modules.pop("worker", None)
        yield
        sys.modules.pop("worker", None)

    @pytest.fixture()
    def worker(self):
        with (
            patch("google.cloud.firestore.Client", return_value=MagicMock()),
            patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=MagicMock()),
            patch("secret_client.get_secret", return_value="fake"),
            patch("google.auth.default", return_value=(MagicMock(), "proj")),
            patch("googleapiclient.discovery.build", return_value=MagicMock()),
        ):
            import worker as w
            yield w

    def _job_with_tokens(self):
        return {
            "job_id": "job-123",
            "file_id": "FILE123",
            "oauth_tokens": dict(SAMPLE_TOKENS),
        }

    def test_drive_404_marks_job_as_failed(self, worker):
        err = Exception("HttpError 404 File not found: FILE123")
        with (
            patch.object(worker, "TEST_MODE", False),
            patch.object(worker, "DOWNLOAD_ONLY", False),
            patch("worker.download_file", side_effect=err),
            patch("worker.fail_job") as mock_fail,
            patch("worker.complete_job") as mock_complete,
        ):
            worker.process_job(self._job_with_tokens())

        mock_fail.assert_called_once_with("job-123", str(err))
        mock_complete.assert_not_called()

    def test_missing_tokens_fails_job_with_descriptive_message(self, worker):
        job = self._job_with_tokens()
        job["oauth_tokens"] = None
        with (
            patch.object(worker, "TEST_MODE", False),
            patch("worker.fail_job") as mock_fail,
        ):
            worker.process_job(job)

        mock_fail.assert_called_once()
        error_msg = mock_fail.call_args[0][1]
        assert "token" in error_msg.lower() or "oauth" in error_msg.lower()

    def test_drive_error_does_not_crash_worker_loop(self, worker):
        """An exception inside process_job must not kill the polling loop."""
        jobs_queue = [self._job_with_tokens()]

        def fake_claim():
            if jobs_queue:
                return jobs_queue.pop(0)
            raise KeyboardInterrupt

        with (
            patch.object(worker, "TEST_MODE", False),
            patch("worker.claim_queued_job", side_effect=fake_claim),
            patch("worker.download_file", side_effect=Exception("404 File not found")),
            patch("worker.fail_job"),
            patch("time.sleep"),
        ):
            worker.run()  # must complete without raising
