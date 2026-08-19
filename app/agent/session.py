from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any, Callable

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.agent.state_machine import ConversationStateMachine
from app.agent.tools import ToolExecutor
from app.core.config import Settings
from app.domain.models import ConversationState
from app.domain.ports import RobotGateway, UserRepository
from app.realtime.client import LiteLLMRealtimeClient
from app.realtime.protocol import parse_function_call, to_frontend_events

logger = logging.getLogger(__name__)


class VoiceSession:
    def __init__(
        self,
        settings: Settings,
        users: UserRepository,
        robot: RobotGateway,
        realtime_factory: Callable[[Settings], LiteLLMRealtimeClient] = LiteLLMRealtimeClient,
    ) -> None:
        self._settings = settings
        self._users = users
        self._robot = robot
        self._realtime_factory = realtime_factory
        self._machine = ConversationStateMachine()
        self._tools = ToolExecutor(self._machine, users, robot)
        self._front_send_lock = asyncio.Lock()
        self._handled_function_calls: set[str] = set()
        self._drawing_monitor: asyncio.Task[None] | None = None
        self._response_idle = asyncio.Event()
        self._response_idle.set()

    async def run(self, frontend: WebSocket) -> None:
        async with self._realtime_factory(self._settings) as realtime:
            await realtime.configure(self._machine)
            await self._send_frontend(
                frontend, {"type": "session.created", "message": "Sesión iniciada"}
            )
            await realtime.create_response(
                "Saluda brevemente como Fulgencio y ofrece una caricatura o un regalo."
            )
            frontend_task = asyncio.create_task(self._receive_frontend(frontend, realtime))
            realtime_task = asyncio.create_task(self._receive_realtime(frontend, realtime))
            tasks = {frontend_task, realtime_task}
            try:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    exception = task.exception()
                    if exception is not None:
                        raise exception
                for task in pending:
                    task.cancel()
            finally:
                for task in tasks:
                    task.cancel()
                if self._drawing_monitor is not None:
                    self._drawing_monitor.cancel()
                    with suppress(asyncio.CancelledError):
                        await self._drawing_monitor
                with suppress(asyncio.CancelledError):
                    await asyncio.gather(*tasks, return_exceptions=True)

    async def _receive_frontend(
        self, frontend: WebSocket, realtime: LiteLLMRealtimeClient
    ) -> None:
        while True:
            message = await frontend.receive()
            if message.get("type") == "websocket.disconnect":
                return
            audio = message.get("bytes")
            if audio is None:
                continue
            if not audio:
                continue
            if len(audio) > self._settings.max_audio_chunk_bytes:
                await self._send_frontend(
                    frontend, {"type": "error", "message": "Fragmento de audio demasiado grande"}
                )
                continue
            if self._machine.state is not ConversationState.FINISHED:
                await realtime.append_audio(audio)

    async def _receive_realtime(
        self, frontend: WebSocket, realtime: LiteLLMRealtimeClient
    ) -> None:
        while True:
            event = await realtime.receive_event()
            if event.get("type") == "response.created":
                self._response_idle.clear()
            elif event.get("type") == "response.done":
                self._response_idle.set()
            for frontend_event in to_frontend_events(event):
                await self._send_frontend(frontend, frontend_event)

            function_call = parse_function_call(event)
            if function_call is None or function_call.call_id in self._handled_function_calls:
                continue
            self._handled_function_calls.add(function_call.call_id)
            await self._send_frontend(
                frontend,
                {
                    "type": "tool_call",
                    "name": function_call.name,
                    "args": function_call.arguments,
                },
            )
            result = await self._tools.execute(
                function_call.call_id, function_call.name, function_call.arguments
            )
            result_payload = result.as_dict()
            await self._send_frontend(
                frontend,
                {"type": "tool_result", "name": function_call.name, "result": result_payload},
            )
            await realtime.send_tool_output(function_call.call_id, result_payload)
            await realtime.configure(self._machine)
            await realtime.create_response()

            if (
                result.status == "ok"
                and self._machine.state is ConversationState.DRAWING
                and self._drawing_monitor is None
            ):
                self._drawing_monitor = asyncio.create_task(
                    self._monitor_drawing(frontend, realtime)
                )

    async def _monitor_drawing(
        self, frontend: WebSocket, realtime: LiteLLMRealtimeClient
    ) -> None:
        try:
            outcome = await self._robot.wait_for_drawing_completion()
            self._machine.finish_drawing()
            await realtime.configure(self._machine)
            await self._interrupt_active_response(realtime)
            if outcome.completed:
                await realtime.create_response(
                    "Anuncia que la caricatura está lista y despídete brevemente."
                )
            else:
                await self._send_frontend(
                    frontend, {"type": "error", "message": outcome.message}
                )
                await realtime.create_response(
                    "Informa brevemente de que el robot no pudo terminar la caricatura. "
                    "No digas que está lista y despídete."
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Drawing monitor failed: %s", type(exc).__name__)
            if self._machine.state is ConversationState.DRAWING:
                self._machine.finish_drawing()
            await self._send_frontend(
                frontend,
                {"type": "error", "message": "No se pudo comprobar el estado del dibujo"},
            )
            await realtime.configure(self._machine)
            await self._interrupt_active_response(realtime)
            await realtime.create_response(
                "Informa de que no puedes confirmar que la caricatura haya terminado. "
                "No afirmes que está lista y despídete."
            )

    async def _interrupt_active_response(self, realtime: LiteLLMRealtimeClient) -> None:
        if self._response_idle.is_set():
            return
        await realtime.cancel_response()
        try:
            await asyncio.wait_for(self._response_idle.wait(), timeout=2)
        except TimeoutError:
            logger.warning("Realtime response cancellation was not acknowledged")

    async def _send_frontend(self, frontend: WebSocket, payload: dict[str, Any]) -> None:
        async with self._front_send_lock:
            try:
                await frontend.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                pass
