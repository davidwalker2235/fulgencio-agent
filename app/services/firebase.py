from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable

import firebase_admin
from firebase_admin import credentials, db

from app.domain.errors import FirebaseError
from app.domain.models import DrawingOutcome, UserRecord


class FirebaseRobotGateway:
    FAILURE_STATES = {"error", "offline"}

    def __init__(
        self,
        database_url: str,
        service_account_json: str,
        *,
        drawing_start_timeout_seconds: float = 60.0,
        drawing_complete_timeout_seconds: float = 300.0,
        clock: Callable[[], float] = time.time,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        try:
            service_account = json.loads(service_account_json)
            credential = credentials.Certificate(service_account)
            self._app = firebase_admin.initialize_app(
                credential,
                {"databaseURL": database_url},
                name=f"fulgencio-agent-{uuid.uuid4().hex}",
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise FirebaseError("La configuración de Firebase no es válida") from exc
        self._root = db.reference("/", app=self._app)
        self._status = db.reference("/status", app=self._app)
        self._robot_action = db.reference("/robot_action", app=self._app)
        self._drawing_start_timeout = drawing_start_timeout_seconds
        self._drawing_complete_timeout = drawing_complete_timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._clock = clock

    async def get_status(self) -> str:
        try:
            value = await asyncio.to_thread(self._status.get)
        except Exception as exc:
            raise FirebaseError("No se pudo leer el estado del robot") from exc
        return str(value or "unknown").strip().lower()

    async def publish_caricature(self, user: UserRecord) -> None:
        action_timestamp = int(self._clock())
        payload = {
            "current_user": user.current_user_payload(),
            "robot_action": user.robot_action_payload(action_timestamp),
        }
        try:
            await asyncio.to_thread(self._root.update, payload)
        except Exception as exc:
            raise FirebaseError("No se pudo enviar la caricatura al robot") from exc

    async def publish_gift(self) -> None:
        payload = {
            "type": "give_gift_bag",
            "timestamp": int(self._clock()),
        }
        try:
            await asyncio.to_thread(self._robot_action.set, payload)
        except Exception as exc:
            raise FirebaseError("No se pudo solicitar el regalo") from exc

    async def wait_for_drawing_completion(
        self,
        *,
        on_start_timeout: Callable[[], Awaitable[None]] | None = None,
        on_late_start: Callable[[], Awaitable[None]] | None = None,
    ) -> DrawingOutcome:
        start_deadline = time.monotonic() + self._drawing_start_timeout
        start_observation = False
        while time.monotonic() < start_deadline:
            status = await self.get_status()
            if status in self.FAILURE_STATES:
                return DrawingOutcome(status, False, "El robot ha informado de un fallo")
            if status == "drawing":
                break
            await asyncio.sleep(self._poll_interval)
        else:
            start_observation = True
            if on_start_timeout is not None:
                await on_start_timeout()

            # Tras el aviso, seguimos observando hasta detectar el arranque real o un fallo.
            while True:
                status = await self.get_status()
                if status in self.FAILURE_STATES:
                    return DrawingOutcome(status, False, "El robot ha informado de un fallo")
                if status == "drawing":
                    if start_observation and on_late_start is not None:
                        await on_late_start()
                    break
                await asyncio.sleep(self._poll_interval)

        completion_deadline = time.monotonic() + self._drawing_complete_timeout
        while time.monotonic() < completion_deadline:
            status = await self.get_status()
            if status in self.FAILURE_STATES:
                return DrawingOutcome(status, False, "El dibujo terminó con un fallo")
            if status == "idle":
                return DrawingOutcome("idle", True, "La caricatura está lista")
            await asyncio.sleep(self._poll_interval)
        return DrawingOutcome("timeout", False, "El dibujo no terminó a tiempo")

    async def check_connection(self) -> None:
        await self.get_status()

    async def close(self) -> None:
        await asyncio.to_thread(firebase_admin.delete_app, self._app)
