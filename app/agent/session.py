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
        conversation_instructions: str | None = None,
    ) -> None:
        self._settings = settings
        self._users = users
        self._robot = robot
        self._realtime_factory = realtime_factory
        self._conversation_instructions = conversation_instructions
        self._machine = ConversationStateMachine()
        self._tools = ToolExecutor(self._machine, users, robot)
        self._front_send_lock = asyncio.Lock()
        self._handled_function_calls: set[str] = set()
        self._response_lock = asyncio.Lock()
        self._response_pending = False
        self._pending_response_instructions: str | None = None
        self._drawing_monitor: asyncio.Task[None] | None = None
        self._drawing_start_observation_active = False
        self._response_idle = asyncio.Event()
        self._response_idle.set()

    async def run(self, frontend: WebSocket) -> None:
        async with self._realtime_factory(self._settings) as realtime:
            await realtime.configure(self._machine, self._conversation_instructions)
            await self._send_frontend(
                frontend, {"type": "session.created", "message": "Sesión iniciada"}
            )
            await self._request_response(
                realtime,
                "Inicia la conversación siguiendo las instrucciones conversacionales vigentes."
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
            event_type = event.get("type")
            if event_type == "response.created":
                self._response_idle.clear()
                response = event.get("response") or {}
                logger.info(
                    "realtime_event type=response.created response_id=%s status=%s",
                    response.get("id"),
                    response.get("status"),
                )
            elif event_type == "response.done":
                response = event.get("response") or {}
                logger.info(
                    "realtime_event type=response.done response_id=%s status=%s",
                    response.get("id"),
                    response.get("status"),
                )
                await self._complete_response(realtime)
            elif event_type == "error":
                error = event.get("error") or {}
                logger.error(
                    "realtime_event type=error code=%s message=%s",
                    error.get("code") if isinstance(error, dict) else None,
                    error.get("message") if isinstance(error, dict) else str(error),
                )
            elif event_type in {
                "input_audio_buffer.speech_started",
                "input_audio_buffer.speech_stopped",
                "input_audio_buffer.committed",
                "response.cancelled",
            }:
                logger.info("realtime_event type=%s", event_type)
            for frontend_event in to_frontend_events(event, include_agent_end=False):
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
            if result.status == "ok" and self._machine.state is ConversationState.FINISHED:
                self._machine.reset_for_next_experience()
            await realtime.configure(self._machine, self._conversation_instructions)
            await self._request_response(realtime)

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
            outcome = await self._robot.wait_for_drawing_completion(
                on_start_timeout=lambda: self._handle_drawing_start_timeout(realtime),
                on_late_start=lambda: self._handle_late_drawing_start(realtime),
            )
            self._drawing_start_observation_active = False
            self._machine.finish_drawing()
            self._machine.reset_for_next_experience()
            await realtime.configure(self._machine, self._conversation_instructions)
            await self._interrupt_active_response(realtime)
            if outcome.completed:
                await self._request_response(
                    realtime,
                    "Anuncia que la caricatura está lista y vuelve a ofrecer las opciones "
                    "disponibles por si el usuario quiere otra experiencia."
                )
            else:
                await self._send_frontend(
                    frontend, {"type": "error", "message": outcome.message}
                )
                await self._request_response(
                    realtime,
                    "Informa brevemente de que el robot no pudo terminar la caricatura. "
                    "No digas que está lista y vuelve a ofrecer las opciones disponibles."
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Drawing monitor failed: %s", type(exc).__name__)
            if self._machine.state is ConversationState.DRAWING:
                self._machine.finish_drawing()
                self._machine.reset_for_next_experience()
            await self._send_frontend(
                frontend,
                {"type": "error", "message": "No se pudo comprobar el estado del dibujo"},
            )
            await realtime.configure(self._machine, self._conversation_instructions)
            await self._interrupt_active_response(realtime)
            await self._request_response(
                realtime,
                "Informa de que no puedes confirmar que la caricatura haya terminado. "
                "No afirmes que está lista y vuelve a ofrecer las opciones disponibles."
            )
        finally:
            self._drawing_monitor = None

    async def _handle_drawing_start_timeout(
        self, realtime: LiteLLMRealtimeClient
    ) -> None:
        if self._machine.state is not ConversationState.DRAWING:
            return
        self._drawing_start_observation_active = True
        await self._request_response(
            realtime,
            "Informa con calma de que parece que el robot todavía no ha empezado a dibujar "
            "la caricatura y que vas a comprobar qué ocurre. No cierres la conversación ni "
            "digas que la caricatura ha terminado.",
        )

    async def _handle_late_drawing_start(
        self, realtime: LiteLLMRealtimeClient
    ) -> None:
        if not self._drawing_start_observation_active:
            return
        self._drawing_start_observation_active = False
        await self._request_response(
            realtime,
            "Informa brevemente y con entusiasmo de que el robot ya está dibujando la "
            "caricatura. Continúa la conversación mientras trabaja.",
        )

    async def _request_response(
        self,
        realtime: LiteLLMRealtimeClient,
        instructions: str | None = None,
    ) -> None:
        async with self._response_lock:
            if not self._response_idle.is_set():
                self._response_pending = True
                if instructions is not None:
                    self._pending_response_instructions = instructions
                return
            self._response_idle.clear()
            try:
                await realtime.create_response(instructions)
            except Exception:
                self._response_idle.set()
                raise

    async def _complete_response(self, realtime: LiteLLMRealtimeClient) -> None:
        async with self._response_lock:
            self._response_idle.set()
            if not self._response_pending:
                return
            instructions = self._pending_response_instructions
            self._response_pending = False
            self._pending_response_instructions = None
            self._response_idle.clear()
            try:
                await realtime.create_response(instructions)
            except Exception:
                self._response_idle.set()
                raise

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
