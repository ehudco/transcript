"""Tests for worker.py — transcription, idle shutdown, and multi-job drain."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call


@pytest.fixture(autouse=True)
def _clean_module():
    sys.modules.pop("worker", None)
    yield
    sys.modules.pop("worker", None)


@pytest.fixture()
def worker():
    with (
        patch("google.cloud.firestore.Client", return_value=MagicMock()),
        patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=MagicMock()),
        patch("secret_client.get_secret", return_value="fake-secret"),
        patch("google.auth.default", return_value=(MagicMock(), "proj")),
        patch("googleapiclient.discovery.build", return_value=MagicMock()),
    ):
        import worker as w
        yield w


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

class TestTranscribe:
    def test_calls_whisperx_with_correct_args(self, worker, tmp_path):
        srt_file = tmp_path / "audio.srt"
        srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nshalom\n", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("subprocess.run", return_value=mock_result) as mock_run,
            patch("glob.glob", return_value=[str(srt_file)]),
            patch("worker.get_secret", return_value="my-hf-token"),
        ):
            content = worker.transcribe("/tmp/audio.mp4")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "whisperx"
        assert "/tmp/audio.mp4" in cmd
        assert "--model" in cmd
        assert "ivrit-ai/whisper-large-v3-ct2" in cmd
        assert "--language" in cmd and "he" in cmd
        assert "--hf_token" in cmd and "my-hf-token" in cmd
        assert "--device" in cmd and "cuda" in cmd
        assert "--output_format" in cmd and "srt" in cmd
        assert content == srt_file.read_text()

    def test_raises_on_nonzero_exit(self, worker):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "CUDA error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="whisperx failed"):
                worker.transcribe("/tmp/audio.mp4")

    def test_raises_when_no_srt_produced(self, worker):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("subprocess.run", return_value=mock_result),
            patch("glob.glob", return_value=[]),
        ):
            with pytest.raises(RuntimeError, match="no .srt file"):
                worker.transcribe("/tmp/audio.mp4")

    def test_hf_token_read_from_secret_manager(self, worker, tmp_path):
        srt_file = tmp_path / "audio.srt"
        srt_file.write_text("content", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("subprocess.run", return_value=mock_result) as mock_run,
            patch("glob.glob", return_value=[str(srt_file)]),
            patch("worker.get_secret", return_value="secret-hf-token") as mock_secret,
        ):
            worker.transcribe("/tmp/audio.mp4")

        mock_secret.assert_called_with("HF_TOKEN")
        cmd = mock_run.call_args[0][0]
        assert "secret-hf-token" in cmd


# ---------------------------------------------------------------------------
# Idle shutdown
# ---------------------------------------------------------------------------

class TestIdleShutdown:
    def test_shuts_down_after_idle_timeout(self, worker):
        elapsed = [0]

        def fake_monotonic():
            elapsed[0] += worker.IDLE_SHUTDOWN_SECONDS + 1
            return elapsed[0]

        with (
            patch.object(worker, "TEST_MODE", False),
            patch("worker.claim_queued_job", return_value=None),
            patch("worker.shutdown_self") as mock_shutdown,
            patch("time.monotonic", side_effect=fake_monotonic),
            patch("time.sleep"),
        ):
            worker.run()

        mock_shutdown.assert_called_once()

    def test_does_not_shut_down_in_test_mode(self, worker):
        call_count = [0]

        def fake_claim():
            call_count[0] += 1
            if call_count[0] >= 3:
                raise KeyboardInterrupt
            return None

        elapsed = [0]
        def fake_monotonic():
            elapsed[0] += worker.IDLE_SHUTDOWN_SECONDS + 1
            return elapsed[0]

        with (
            patch.object(worker, "TEST_MODE", True),
            patch("worker.claim_queued_job", side_effect=fake_claim),
            patch("worker.shutdown_self") as mock_shutdown,
            patch("time.monotonic", side_effect=fake_monotonic),
            patch("time.sleep"),
        ):
            worker.run()

        mock_shutdown.assert_not_called()

    def test_idle_timer_resets_after_job(self, worker):
        job = {"job_id": "j1", "file_id": "f1", "oauth_tokens": None}
        calls = [0]

        def fake_claim():
            calls[0] += 1
            if calls[0] == 1:
                return job
            raise KeyboardInterrupt

        with (
            patch.object(worker, "TEST_MODE", False),
            patch("worker.claim_queued_job", side_effect=fake_claim),
            patch("worker.process_job"),
            patch("worker.shutdown_self") as mock_shutdown,
            patch("time.sleep"),
        ):
            worker.run()

        mock_shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# Multi-job drain
# ---------------------------------------------------------------------------

class TestMultiJobDrain:
    def test_processes_all_queued_jobs_without_sleeping(self, worker):
        jobs = [
            {"job_id": "j1", "file_id": "f1", "oauth_tokens": None},
            {"job_id": "j2", "file_id": "f2", "oauth_tokens": None},
            {"job_id": "j3", "file_id": "f3", "oauth_tokens": None},
        ]
        claim_returns = jobs + [KeyboardInterrupt()]

        def fake_claim():
            val = claim_returns.pop(0)
            if isinstance(val, KeyboardInterrupt):
                raise val
            return val

        sleep_calls = []

        with (
            patch.object(worker, "TEST_MODE", False),
            patch("worker.claim_queued_job", side_effect=fake_claim),
            patch("worker.process_job") as mock_process,
            patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)),
        ):
            worker.run()

        assert mock_process.call_count == 3
        assert len(sleep_calls) == 0
