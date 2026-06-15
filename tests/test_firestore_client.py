"""Tests for firestore_client.py — all CRUD helpers."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch


@pytest.fixture()
def mock_db():
    return MagicMock()


@pytest.fixture(autouse=True)
def _patch_firestore(mock_db):
    with patch("google.cloud.firestore.Client", return_value=mock_db):
        import sys
        sys.modules.pop("firestore_client", None)
        yield
        sys.modules.pop("firestore_client", None)


# Helper to get the module after patching
@pytest.fixture()
def fc(mock_db):
    import firestore_client
    firestore_client.db = mock_db
    return firestore_client


# ── Users ──────────────────────────────────────────────────────────────────

class TestGetUser:
    def test_returns_dict_when_exists(self, fc, mock_db):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"email": "a@b.com", "status": "active"}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        result = fc.get_user("a@b.com")

        assert result == {"email": "a@b.com", "status": "active"}
        mock_db.collection.assert_called_with("users")
        mock_db.collection.return_value.document.assert_called_with("a@b.com")

    def test_returns_none_when_missing(self, fc, mock_db):
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        assert fc.get_user("nobody@example.com") is None


class TestCreatePendingUser:
    def test_sets_correct_fields(self, fc, mock_db):
        fc.create_pending_user("new@example.com", "google-sub-123")

        mock_db.collection.assert_called_with("users")
        mock_db.collection.return_value.document.assert_called_with("new@example.com")
        set_call = mock_db.collection.return_value.document.return_value.set
        set_call.assert_called_once()
        data = set_call.call_args[0][0]

        assert data["email"] == "new@example.com"
        assert data["sub"] == "google-sub-123"
        assert data["status"] == "pending"
        assert data["role"] == "user"
        assert data["approved_by"] is None
        assert data["last_login"] is None
        assert isinstance(data["created_at"], datetime)


class TestApproveUser:
    def test_sets_status_active_and_approver(self, fc, mock_db):
        fc.approve_user("user@example.com", "admin@example.com")

        update = mock_db.collection.return_value.document.return_value.update
        update.assert_called_once()
        data = update.call_args[0][0]

        assert data["status"] == "active"
        assert data["approved_by"] == "admin@example.com"
        assert isinstance(data["approved_at"], datetime)


class TestBlockUser:
    def test_sets_status_blocked(self, fc, mock_db):
        fc.block_user("user@example.com")

        update = mock_db.collection.return_value.document.return_value.update
        update.assert_called_once_with({"status": "blocked"})


class TestSetUserRole:
    def test_updates_role_field(self, fc, mock_db):
        fc.set_user_role("user@example.com", "admin")

        update = mock_db.collection.return_value.document.return_value.update
        update.assert_called_once_with({"role": "admin"})


class TestDeleteUser:
    def test_calls_delete(self, fc, mock_db):
        fc.delete_user("user@example.com")

        mock_db.collection.return_value.document.return_value.delete.assert_called_once()


class TestListUsers:
    def test_returns_list_of_dicts(self, fc, mock_db):
        docs = [MagicMock(), MagicMock()]
        docs[0].to_dict.return_value = {"email": "a@b.com"}
        docs[1].to_dict.return_value = {"email": "c@d.com"}
        mock_db.collection.return_value.stream.return_value = iter(docs)

        result = fc.list_users()

        assert result == [{"email": "a@b.com"}, {"email": "c@d.com"}]


class TestUpdateUserLastLogin:
    def test_updates_last_login(self, fc, mock_db):
        fc.update_user_last_login("user@example.com")

        update = mock_db.collection.return_value.document.return_value.update
        update.assert_called_once()
        data = update.call_args[0][0]
        assert "last_login" in data
        assert isinstance(data["last_login"], datetime)


# ── Jobs ───────────────────────────────────────────────────────────────────

class TestCreateJob:
    def test_sets_correct_fields(self, fc, mock_db):
        tokens = {"token": "t", "refresh_token": "r"}
        fc.create_job("job-123", "user@example.com", "file-abc", "my_file.mp4", oauth_tokens=tokens)

        set_call = mock_db.collection.return_value.document.return_value.set
        set_call.assert_called_once()
        data = set_call.call_args[0][0]

        assert data["job_id"] == "job-123"
        assert data["user_email"] == "user@example.com"
        assert data["file_id"] == "file-abc"
        assert data["file_name"] == "my_file.mp4"
        assert data["status"] == "queued"
        assert data["oauth_tokens"] == tokens
        assert data["srt_content"] is None
        assert data["error"] is None
        assert isinstance(data["created_at"], datetime)

    def test_oauth_tokens_defaults_to_none(self, fc, mock_db):
        fc.create_job("job-456", "user@example.com", "file-xyz", "file.mp4")
        data = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
        assert data["oauth_tokens"] is None


class TestGetJob:
    def test_returns_dict_when_exists(self, fc, mock_db):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"job_id": "j1"}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        assert fc.get_job("j1") == {"job_id": "j1"}

    def test_returns_none_when_missing(self, fc, mock_db):
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        assert fc.get_job("nope") is None


class TestListUserJobs:
    def test_queries_by_email_descending(self, fc, mock_db):
        from datetime import datetime, timezone
        docs = [MagicMock(), MagicMock()]
        docs[0].to_dict.return_value = {"job_id": "j1", "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
        docs[1].to_dict.return_value = {"job_id": "j2", "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc)}

        mock_db.collection.return_value.where.return_value.stream.return_value = iter(docs)

        result = fc.list_user_jobs("user@example.com")

        mock_db.collection.assert_called_with("jobs")
        mock_db.collection.return_value.where.assert_called_once_with("user_email", "==", "user@example.com")
        # Sorted descending by created_at
        assert result == [
            {"job_id": "j2", "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc)},
            {"job_id": "j1", "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        ]


class TestClaimQueuedJob:
    def test_returns_none_when_no_queued_jobs(self, fc, mock_db):
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = iter([])
        assert fc.claim_queued_job() is None

    def test_claims_job_and_sets_processing(self, fc, mock_db):
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {"job_id": "j1", "status": "queued"}
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = iter([mock_doc])

        result = fc.claim_queued_job()

        mock_doc.reference.update.assert_called_once()
        update_data = mock_doc.reference.update.call_args[0][0]
        assert update_data["status"] == "processing"
        assert isinstance(update_data["started_at"], datetime)
        assert result["job_id"] == "j1"


class TestCompleteJob:
    def test_sets_completed_and_clears_tokens(self, fc, mock_db):
        fc.complete_job("j1", "1\n00:00:00,000 --> 00:00:01,000\nHello\n")

        update = mock_db.collection.return_value.document.return_value.update
        update.assert_called_once()
        data = update.call_args[0][0]
        assert data["status"] == "completed"
        assert data["oauth_tokens"] is None
        assert "Hello" in data["srt_content"]
        assert isinstance(data["completed_at"], datetime)


class TestFailJob:
    def test_sets_error_and_clears_tokens(self, fc, mock_db):
        fc.fail_job("j1", "something went wrong")

        update = mock_db.collection.return_value.document.return_value.update
        update.assert_called_once()
        data = update.call_args[0][0]
        assert data["status"] == "error"
        assert data["error"] == "something went wrong"
        assert data["oauth_tokens"] is None
        assert isinstance(data["completed_at"], datetime)


class TestListAllJobs:
    def test_returns_all_jobs_sorted(self, fc, mock_db):
        from datetime import datetime, timezone
        docs = [MagicMock(), MagicMock()]
        docs[0].to_dict.return_value = {"job_id": "j1", "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
        docs[1].to_dict.return_value = {"job_id": "j2", "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc)}

        mock_db.collection.return_value.stream.return_value = iter(docs)

        result = fc.list_all_jobs()

        # Sorted descending by created_at
        assert result == [
            {"job_id": "j2", "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc)},
            {"job_id": "j1", "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        ]
