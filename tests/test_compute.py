"""Tests for compute.py — get_vm_status, start_vm, stop_vm."""

import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture()
def mock_compute_service():
    """A mock Google Compute v1 service object."""
    service = MagicMock()
    return service


@pytest.fixture(autouse=True)
def _patch_compute(mock_compute_service):
    with (
        patch("google.auth.default", return_value=(MagicMock(), "test-project")),
        patch("googleapiclient.discovery.build", return_value=mock_compute_service),
    ):
        import sys
        sys.modules.pop("compute", None)
        yield
        sys.modules.pop("compute", None)


class TestGetVmStatus:
    def test_returns_status_string(self, mock_compute_service):
        mock_compute_service.instances.return_value.get.return_value.execute.return_value = {
            "status": "RUNNING"
        }

        import compute
        status = compute.get_vm_status()

        assert status == "RUNNING"

    def test_missing_status_key_returns_unknown(self, mock_compute_service):
        mock_compute_service.instances.return_value.get.return_value.execute.return_value = {}

        import compute
        assert compute.get_vm_status() == "UNKNOWN"

    def test_calls_correct_project_zone_instance(self, mock_compute_service):
        mock_compute_service.instances.return_value.get.return_value.execute.return_value = {
            "status": "TERMINATED"
        }

        import compute
        compute.get_vm_status()

        mock_compute_service.instances.return_value.get.assert_called_once_with(
            project=compute.PROJECT_ID,
            zone=compute.ZONE,
            instance=compute.INSTANCE_NAME,
        )


class TestStartVm:
    def test_calls_start(self, mock_compute_service):
        import compute
        compute.start_vm()

        mock_compute_service.instances.return_value.start.assert_called_once_with(
            project=compute.PROJECT_ID,
            zone=compute.ZONE,
            instance=compute.INSTANCE_NAME,
        )
        mock_compute_service.instances.return_value.start.return_value.execute.assert_called_once()


class TestStopVm:
    def test_calls_stop(self, mock_compute_service):
        import compute
        compute.stop_vm()

        mock_compute_service.instances.return_value.stop.assert_called_once_with(
            project=compute.PROJECT_ID,
            zone=compute.ZONE,
            instance=compute.INSTANCE_NAME,
        )
        mock_compute_service.instances.return_value.stop.return_value.execute.assert_called_once()
