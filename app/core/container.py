from __future__ import annotations

import asyncio
import time

import httpx

from app.agent.session import VoiceSession
from app.core.config import Settings
from app.core.session_gate import SingleSessionGate
from app.services.azure_sql import AzureSqlUserRepository
from app.services.firebase import FirebaseRobotGateway


class AppContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session_gate = SingleSessionGate()
        self.users: AzureSqlUserRepository | None = None
        self.robot: FirebaseRobotGateway | None = None
        self._readiness_lock = asyncio.Lock()
        self._readiness_checked_at = float("-inf")
        self._readiness_cache: list[str] = ["not_checked"]

    async def start(self) -> None:
        self.settings.assert_runtime_ready()
        self.users = AzureSqlUserRepository(
            self.settings.azure_sql_connection_string,
            timeout_seconds=self.settings.azure_sql_connect_timeout_seconds,
            retry_attempts=self.settings.azure_sql_connect_retry_attempts,
            retry_base_seconds=self.settings.azure_sql_connect_retry_base_seconds,
            retry_max_total_seconds=self.settings.azure_sql_connect_max_total_seconds,
        )
        self.robot = FirebaseRobotGateway(
            self.settings.firebase_database_url,
            self.settings.firebase_service_account_json,
            drawing_start_timeout_seconds=self.settings.drawing_start_timeout_seconds,
            drawing_complete_timeout_seconds=self.settings.drawing_complete_timeout_seconds,
        )

    async def close(self) -> None:
        if self.robot is not None:
            await self.robot.close()

    def create_voice_session(
        self, conversation_instructions: str | None = None
    ) -> VoiceSession:
        if self.users is None or self.robot is None:
            raise RuntimeError("Las dependencias no están inicializadas")
        return VoiceSession(
            self.settings,
            self.users,
            self.robot,
            conversation_instructions=conversation_instructions,
        )

    async def readiness_errors(self) -> list[str]:
        if self.users is None or self.robot is None:
            return ["dependencies"]
        async with self._readiness_lock:
            if time.monotonic() - self._readiness_checked_at < 10:
                return list(self._readiness_cache)
            self._readiness_cache = await self._run_readiness_checks()
            self._readiness_checked_at = time.monotonic()
            return list(self._readiness_cache)

    async def _run_readiness_checks(self) -> list[str]:
        assert self.users is not None and self.robot is not None

        async def check_litellm() -> None:
            headers = {"Authorization": f"Bearer {self.settings.litellm_proxy_api_key}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.settings.litellm_proxy_http_url}/health/liveliness",
                    headers=headers,
                )
                response.raise_for_status()

        checks = {
            "azure_sql": self.users.check_connection(),
            "firebase": self.robot.check_connection(),
            "litellm": check_litellm(),
        }
        results = await asyncio.gather(*checks.values(), return_exceptions=True)
        return [name for name, result in zip(checks, results) if isinstance(result, Exception)]
