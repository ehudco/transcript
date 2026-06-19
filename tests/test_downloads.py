"""Tests for Hebrew SRT, English SRT, and CSV download endpoints."""

import pytest
from unittest.mock import patch

HEBREW_SRT = "1\n00:00:00,000 --> 00:00:02,000\nשלום עולם\n"
ENGLISH_SRT = "1\n00:00:00,000 --> 00:00:02,000\nHello world\n"
CSV_CONTENT = "subtitle_number,timestamps,hebrew_subtitle,english_subtitle\n1,00:00:00,000 --> 00:00:02,000,שלום עולם,Hello world\n"


def _completed_job(job_id="job-123", user_email="user@example.com", **extra):
    return {
        "job_id": job_id,
        "user_email": user_email,
        "file_name": "session.mp4",
        "status": "completed",
        "srt_content": HEBREW_SRT,
        "srt_translated": ENGLISH_SRT,
        "translation_status": "completed",
        "csv_content": CSV_CONTENT,
        **extra,
    }


class TestDownloadHebrew:
    async def test_unauthenticated_redirects(self, client):
        resp = await client.get("/job/job-123/download", follow_redirects=False)
        assert resp.status_code in (302, 307)

    async def test_returns_srt_content(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download", follow_redirects=False)
        assert resp.status_code == 200
        assert HEBREW_SRT.encode() in resp.content

    async def test_filename_has_srt_extension(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download", follow_redirects=False)
        assert resp.status_code == 200
        assert "session.srt" in resp.headers["content-disposition"]

    async def test_other_users_job_returns_403(self, user_client):
        job = _completed_job(user_email="other@example.com")
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download", follow_redirects=False)
        assert resp.status_code == 403

    async def test_missing_job_returns_404(self, user_client):
        with patch("jobs.get_job", return_value=None):
            resp = await user_client.get("/job/job-123/download", follow_redirects=False)
        assert resp.status_code == 404

    async def test_not_completed_returns_404(self, user_client):
        job = _completed_job(status="processing", srt_content=None)
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download", follow_redirects=False)
        assert resp.status_code == 404


class TestDownloadEnglish:
    async def test_unauthenticated_redirects(self, client):
        resp = await client.get("/job/job-123/download-translation", follow_redirects=False)
        assert resp.status_code in (302, 307)

    async def test_returns_english_srt_content(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download-translation", follow_redirects=False)
        assert resp.status_code == 200
        assert ENGLISH_SRT.encode() in resp.content

    async def test_filename_has_english_srt_extension(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download-translation", follow_redirects=False)
        assert "session_english.srt" in resp.headers["content-disposition"]

    async def test_other_users_job_returns_403(self, user_client):
        job = _completed_job(user_email="other@example.com")
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download-translation", follow_redirects=False)
        assert resp.status_code == 403

    async def test_translation_not_ready_returns_404(self, user_client):
        job = _completed_job(translation_status="translating", srt_translated=None)
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download-translation", follow_redirects=False)
        assert resp.status_code == 404

    async def test_translation_failed_returns_404(self, user_client):
        job = _completed_job(translation_status="failed", srt_translated=None)
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download-translation", follow_redirects=False)
        assert resp.status_code == 404


class TestDownloadCsv:
    async def test_unauthenticated_redirects(self, client):
        resp = await client.get("/job/job-123/download-csv", follow_redirects=False)
        assert resp.status_code in (302, 307)

    async def test_returns_csv_content(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert resp.status_code == 200
        assert b"hebrew_subtitle" in resp.content
        assert b"english_subtitle" in resp.content

    async def test_filename_has_csv_extension(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert "session.csv" in resp.headers["content-disposition"]

    async def test_content_type_is_csv(self, user_client):
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert "text/csv" in resp.headers["content-type"]

    async def test_other_users_job_returns_403(self, user_client):
        job = _completed_job(user_email="other@example.com")
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert resp.status_code == 403

    async def test_csv_not_ready_returns_404(self, user_client):
        job = _completed_job(csv_content=None)
        with patch("jobs.get_job", return_value=job):
            resp = await user_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert resp.status_code == 404

    async def test_admin_can_download_any_users_csv(self, admin_client):
        job = _completed_job(user_email="someone@example.com")
        with patch("jobs.get_job", return_value=job):
            resp = await admin_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert resp.status_code == 200

    async def test_csv_has_utf8_bom_for_excel(self, user_client):
        """CSV must start with UTF-8 BOM so Excel opens Hebrew correctly."""
        with patch("jobs.get_job", return_value=_completed_job()):
            resp = await user_client.get("/job/job-123/download-csv", follow_redirects=False)
        assert resp.content[:3] == b"\xef\xbb\xbf"
