from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import pyodbc

from app.domain.errors import AzureSqlError
from app.domain.models import UserRecord


class AzureSqlUserRepository:
    FIELDS = (
        "id",
        "full_name",
        "email",
        "timestamp",
        "real_name",
        "work_name",
        "request_id",
        "caricature",
        "caricature_timestamp",
    )

    def __init__(
        self,
        connection_string: str,
        *,
        timeout_seconds: int = 60,
        retry_attempts: int = 5,
        retry_base_seconds: float = 1.0,
        retry_max_total_seconds: float = 45.0,
    ) -> None:
        self._raw_connection_string = connection_string.strip()
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_total_seconds = retry_max_total_seconds

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        return await asyncio.to_thread(self._get_by_id_sync, user_id)

    async def check_connection(self) -> None:
        await asyncio.to_thread(self._check_connection_sync)

    def _get_by_id_sync(self, user_id: int) -> UserRecord | None:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT id, full_name, email, [timestamp], real_name, work_name,
                       request_id, caricature, caricature_timestamp
                FROM users
                WHERE id = ?;
                """,
                (int(user_id),),
            )
            row = cursor.fetchone()
        except pyodbc.Error as exc:
            raise AzureSqlError("No se pudo consultar el usuario en Azure SQL") from exc
        finally:
            connection.close()
        if row is None:
            return None
        values: dict[str, Any] = dict(zip(self.FIELDS, row))
        return UserRecord(**values)

    def _check_connection_sync(self) -> None:
        connection = self._connect()
        connection.close()

    def _connect(self):
        connection_string = self._connection_string()
        attempts = max(1, self._retry_attempts)
        started_at = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return pyodbc.connect(connection_string, timeout=self._timeout_seconds)
            except pyodbc.Error as exc:
                last_error = exc
                elapsed = time.monotonic() - started_at
                if (
                    attempt >= attempts
                    or not self._is_transient(exc)
                    or elapsed >= self._retry_max_total_seconds
                ):
                    raise AzureSqlError("No se pudo conectar con Azure SQL") from exc
                delay = self._retry_base_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, self._retry_base_seconds)
                delay = min(delay, max(0.1, self._retry_max_total_seconds - elapsed))
                time.sleep(delay)
        raise AzureSqlError("No se pudo conectar con Azure SQL") from last_error

    def _connection_string(self) -> str:
        if not self._raw_connection_string:
            raise AzureSqlError("AZURE_SQL_CONNECTION_STRING no está configurado")
        value = self._normalize(self._raw_connection_string)
        if "DRIVER=" in value.upper():
            return value
        installed = set(pyodbc.drivers())
        candidates = (
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 13 for SQL Server",
        )
        driver = next((name for name in candidates if name in installed), candidates[0])
        return f"Driver={{{driver}}};{value}"

    @staticmethod
    def _normalize(raw: str) -> str:
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        replacements = {
            "Encrypt=True": "Encrypt=yes",
            "Encrypt=False": "Encrypt=no",
            "TrustServerCertificate=True": "TrustServerCertificate=yes",
            "TrustServerCertificate=False": "TrustServerCertificate=no",
            "MultipleActiveResultSets=True": "MARS_Connection=yes",
            "MultipleActiveResultSets=False": "MARS_Connection=no",
            "Persist Security Info=False;": "",
            "Persist Security Info=True;": "",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        if "INITIAL CATALOG=" in value.upper() and "DATABASE=" not in value.upper():
            value = value.replace("Initial Catalog=", "Database=")
        if "USER ID=" in value.upper() and "UID=" not in value.upper():
            value = value.replace("User ID=", "UID=")
        if "PASSWORD=" in value.upper() and "PWD=" not in value.upper():
            value = value.replace("Password=", "PWD=")
        return value

    @staticmethod
    def _is_transient(error: Exception) -> bool:
        message = str(error).lower()
        return any(
            marker in message
            for marker in (
                "hyt00",
                "08001",
                "08s01",
                "40613",
                "40197",
                "40501",
                "49918",
                "49919",
                "49920",
                "10928",
                "10929",
                "not currently available",
                "service is currently busy",
                "timed out",
                "timeout",
                "tcp provider",
                "connection is busy",
            )
        )

