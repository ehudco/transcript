"""Tests for jobs.py — parse_drive_file_id, submit, job_status, my-jobs."""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Pure unit tests — no HTTP
# ---------------------------------------------------------------------------

class TestParseDriveFileId:
    # Import lazily so the module is loaded after patches in conftest.
    @pytest.fixture(autouse=True)
    def _import(self):
        import sys
        import jobs as jobs_module
        self.parse = jobs_module.parse_drive_file_id

    def test_file_url_format(self):
        url = "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view"
        assert self.parse(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    def test_open_url_id_param(self):
        url = "https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        assert self.parse(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    def test_uc_download_url(self):
        url = "https://drive.google.com/uc?export=download&id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
        assert self.parse(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    def test_d_shortlink(self):
        url = "https://drive.google.com/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/preview"
        assert self.parse(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    def test_invalid_url_returns_none(self):
        assert self.parse("https://example.com/not-a-drive-url") is None

    def test_empty_string_returns_none(self):
        assert self.parse("") is None

    def test_id_with_hyphens_and_underscores(self):
        url = "https://drive.google.com/file/d/1a-B_C2dEfG/view"
        assert self.parse(url) == "1a-B_C2dEfG"


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------

class TestSubmitJob:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.post(
            "/submit",
            data={"drive_url": "https://drive.google.com/file/d/abc123/view"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/login")

    async def test_invalid_url_shows_error(self, user_client):
        resp = await user_client.post(
            "/submit",
            data={"drive_url": "not-a-drive-url"},
            follow_redirects=False,
        )
        # Returns the dashboard template with an error (200) — NOT a redirect.
        assert resp.status_code == 200
        assert b"Could not parse" in resp.content or b"Drive file ID" in resp.content

    async def test_valid_url_in_test_mode_creates_job_and_redirects(self, user_client):
        with (
            patch("jobs.create_job") as mock_create,
            patch.dict("os.environ", {"TEST_MODE": "true"}),
        ):
            resp = await user_client.post(
                "/submit",
                data={"drive_url": "https://drive.google.com/file/d/FILE_ID_123/view"},
                follow_redirects=False,
            )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["file_id"] == "FILE_ID_123"
        assert call_kwargs["user_email"] == "user@example.com"
        assert resp.status_code in (302, 303, 307)
        assert "/job/" in resp.headers["location"]

    async def test_valid_url_starts_vm_when_terminated(self, user_client):
        with (
            patch("jobs.create_job"),
            patch("jobs.TEST_MODE", False),
            patch("compute.get_vm_status", return_value="TERMINATED"),
            patch("compute.start_vm") as mock_start,
            patch("google.cloud.pubsub_v1.PublisherClient") as mock_pub,
        ):
            mock_pub.return_value.topic_path.return_value = "projects/p/topics/t"
            mock_pub.return_value.publish.return_value = MagicMock()

            resp = await user_client.post(
                "/submit",
                data={"drive_url": "https://drive.google.com/file/d/FILE_ID/view"},
                follow_redirects=False,
            )

        mock_start.assert_called_once()

    async def test_valid_url_skips_start_when_vm_running(self, user_client):
        with (
            patch("jobs.create_job"),
            patch("jobs.TEST_MODE", False),
            patch("compute.get_vm_status", return_value="RUNNING"),
            patch("compute.start_vm") as mock_start,
            patch("google.cloud.pubsub_v1.PublisherClient") as mock_pub,
        ):
            mock_pub.return_value.topic_path.return_value = "projects/p/topics/t"
            mock_pub.return_value.publish.return_value = MagicMock()

            await user_client.post(
                "/submit",
                data={"drive_url": "https://drive.google.com/file/d/FILE_ID/view"},
                follow_redirects=False,
            )

        mock_start.assert_not_called()


class TestJobStatus:
    async def test_unauthenticated_redirects(self, client):
        resp = await client.get("/job/some-job-id", follow_redirects=False)
        assert resp.status_code in (302, 307)

    async def test_missing_job_returns_404(self, user_client):
        with patch("jobs.get_job", return_value=None):
            resp = await user_client.get("/job/nonexistent", follow_redirects=False)
        assert resp.status_code == 404

    async def test_other_users_job_returns_403(self, user_client):
        job = {"job_id": "j1", "user_email": "other@example.com", "status": "queued"}
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/j1", follow_redirects=False)
        assert resp.status_code == 403

    async def test_owner_can_view_job(self, user_client):
        job = {"job_id": "j1", "user_email": "user@example.com", "status": "queued"}
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/j1", follow_redirects=False)
        assert resp.status_code not in (403, 302, 307)

    async def test_admin_can_view_any_job(self, admin_client):
        job = {"job_id": "j1", "user_email": "someone-else@example.com", "status": "done"}
        with patch("jobs.get_job", return_value=job):
            resp = await admin_client.get("/job/j1", follow_redirects=False)
        assert resp.status_code != 403


class TestMyJobs:
    async def test_unauthenticated_redirects(self, client):
        resp = await client.get("/my-jobs", follow_redirects=False)
        assert resp.status_code in (302, 307)

    async def test_returns_users_jobs(self, user_client):
        jobs = [{"job_id": "j1", "user_email": "user@example.com", "status": "done"}]
        with patch("jobs.list_user_jobs", return_value=jobs) as mock_list:
            resp = await user_client.get("/my-jobs", follow_redirects=False)
        mock_list.assert_called_once_with("user@example.com")
        assert resp.status_code not in (302, 307, 403)
