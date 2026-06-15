"""Tests for worker.py — idle shutdown and multi-job drain."""

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
        patch("secret_client.get_secret", return_value="fake"),
        patch("google.auth.default", return_value=(MagicMock(), "proj")),
        patch("googleapiclient.discovery.build", return_value=MagicMock()),
    ):
        import worker as w
        yield w


class TestIdleShutdown:
    def test_shuts_down_after_idle_timeout(self, worker):
        """When no jobs appear for IDLE_SHUTDOWN_SECONDS, shutdown_self() is called."""
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
        """Idle shutdown is skipped when TEST_MODE=true."""
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
        """Completing a job resets the idle timer so shutdown is deferred."""
        job = {"job_id": "j1", "file_id": "f1", "oauth_tokens": None}
        calls = [0]

        def fake_claim():
            calls[0] += 1
            if calls[0] == 1:
                return job       # first call: job available
            if calls[0] == 2:
                raise KeyboardInterrupt  # second call: stop
            return None

        with (
            patch.object(worker, "TEST_MODE", False),
            patch("worker.claim_queued_job", side_effect=fake_claim),
            patch("worker.process_job"),
            patch("worker.shutdown_self") as mock_shutdown,
            patch("time.sleep"),
        ):
            worker.run()

        mock_shutdown.assert_not_called()


class TestMultiJobDrain:
    def test_processes_all_queued_jobs_without_sleeping(self, worker):
        """When multiple jobs are queued, they are all processed before any sleep."""
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
        # No sleep should have happened between the three jobs
        assert len(sleep_calls) == 0
