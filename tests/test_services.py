from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import pyodbc

from app.domain.models import UserRecord
from app.services.azure_sql import AzureSqlUserRepository
from app.services.firebase import FirebaseRobotGateway


class FakeReference:
    def __init__(self) -> None:
        self.updated = None
        self.value = None

    def update(self, value):
        self.updated = value

    def set(self, value):
        self.value = value


class FirebaseGatewayTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self) -> FirebaseRobotGateway:
        gateway = object.__new__(FirebaseRobotGateway)
        gateway._root = FakeReference()
        gateway._robot_action = FakeReference()
        gateway._clock = lambda: 1234567890
        gateway._drawing_start_timeout = 0.05
        gateway._drawing_complete_timeout = 0.05
        gateway._poll_interval = 0
        return gateway

    async def test_atomic_caricature_and_gift_documents(self) -> None:
        gateway = self.gateway()
        record = UserRecord(7, "Ada", "ada@example.com", "date", caricature="image")
        await gateway.publish_caricature(record)
        self.assertEqual(set(gateway._root.updated), {"current_user", "robot_action"})
        self.assertEqual(gateway._root.updated["robot_action"]["type"], "draw_caricature")
        await gateway.publish_gift()
        self.assertEqual(
            gateway._robot_action.value,
            {"type": "give_gift_bag", "timestamp": 1234567890},
        )

    async def test_waits_for_drawing_then_idle(self) -> None:
        gateway = self.gateway()
        statuses = iter(["idle", "thinking", "drawing", "drawing", "idle"])

        async def status() -> str:
            return next(statuses)

        gateway.get_status = status
        outcome = await gateway.wait_for_drawing_completion()
        self.assertTrue(outcome.completed)
        self.assertEqual(outcome.status, "idle")

    async def test_error_and_offline_are_failures(self) -> None:
        for terminal_status in ("error", "offline"):
            gateway = self.gateway()

            async def status(value=terminal_status) -> str:
                return value

            gateway.get_status = status
            outcome = await gateway.wait_for_drawing_completion()
            self.assertFalse(outcome.completed)
            self.assertEqual(outcome.status, terminal_status)


class AzureRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_exact_users_columns(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = (
            5,
            "Ada",
            "ada@example.com",
            "timestamp",
            "real",
            "work",
            "request",
            "image",
            "caricature-time",
        )
        connection = Mock()
        connection.cursor.return_value = cursor
        repository = AzureSqlUserRepository("Server=x;Database=y;UID=u;PWD=p")
        with patch.object(pyodbc, "drivers", return_value=["ODBC Driver 18 for SQL Server"]), patch.object(
            pyodbc, "connect", return_value=connection
        ):
            record = await repository.get_by_id(5)
        self.assertEqual(record, UserRecord(5, "Ada", "ada@example.com", "timestamp", "real", "work", "request", "image", "caricature-time"))
        cursor.execute.assert_called_once()
        connection.close.assert_called_once()

    def test_transient_errors_are_detected(self) -> None:
        self.assertTrue(AzureSqlUserRepository._is_transient(Exception("HYT00 timeout")))
        self.assertFalse(AzureSqlUserRepository._is_transient(Exception("syntax error")))

    def test_transient_connection_is_retried(self) -> None:
        connection = Mock()
        repository = AzureSqlUserRepository(
            "Server=x;Database=y;UID=u;PWD=p",
            retry_attempts=2,
            retry_base_seconds=0,
        )
        with patch.object(pyodbc, "drivers", return_value=["ODBC Driver 18 for SQL Server"]), patch.object(
            pyodbc,
            "connect",
            side_effect=[pyodbc.Error("HYT00 timeout"), connection],
        ) as connect, patch("app.services.azure_sql.time.sleep"):
            self.assertIs(repository._connect(), connection)
        self.assertEqual(connect.call_count, 2)
