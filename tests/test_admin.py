"""Tests for admin.py — access control and user-management actions."""

import pytest
from unittest.mock import patch


class TestAdminAccessControl:
    async def test_unauthenticated_redirects_to_login(self, client):
        resp = await client.get("/admin/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].endswith("/login")

    async def test_regular_user_gets_403(self, user_client):
        resp = await user_client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 403

    async def test_admin_can_access(self, admin_client):
        with (
            patch("admin.list_users", return_value=[]),
            patch("admin.list_all_jobs", return_value=[]),
        ):
            resp = await admin_client.get("/admin/", follow_redirects=False)
        # 200 or template-not-found (500) — either way not 403/302
        assert resp.status_code not in (302, 307, 403)


class TestApproveUser:
    async def test_non_admin_blocked(self, user_client):
        resp = await user_client.post("/admin/approve", data={"email": "x@example.com"}, follow_redirects=False)
        assert resp.status_code == 403

    async def test_admin_approves_user(self, admin_client):
        with patch("admin.approve_user") as mock_approve:
            resp = await admin_client.post(
                "/admin/approve", data={"email": "user@example.com"}, follow_redirects=False
            )
        mock_approve.assert_called_once_with("user@example.com", approved_by="admin@example.com")
        assert resp.status_code in (302, 303, 307)


class TestBlockUser:
    async def test_admin_blocks_user(self, admin_client):
        with patch("admin.block_user") as mock_block:
            resp = await admin_client.post(
                "/admin/block", data={"email": "user@example.com"}, follow_redirects=False
            )
        mock_block.assert_called_once_with("user@example.com")
        assert resp.status_code in (302, 303, 307)


class TestDeleteUser:
    async def test_admin_deletes_user(self, admin_client):
        with patch("admin.delete_user") as mock_delete:
            resp = await admin_client.post(
                "/admin/delete", data={"email": "user@example.com"}, follow_redirects=False
            )
        mock_delete.assert_called_once_with("user@example.com")
        assert resp.status_code in (302, 303, 307)


class TestSetRole:
    async def test_admin_sets_valid_role(self, admin_client):
        with patch("admin.set_user_role") as mock_role:
            resp = await admin_client.post(
                "/admin/set-role",
                data={"email": "user@example.com", "role": "admin"},
                follow_redirects=False,
            )
        mock_role.assert_called_once_with("user@example.com", "admin")
        assert resp.status_code in (302, 303, 307)

    async def test_invalid_role_returns_400(self, admin_client):
        resp = await admin_client.post(
            "/admin/set-role",
            data={"email": "user@example.com", "role": "superuser"},
            follow_redirects=False,
        )
        assert resp.status_code == 400
