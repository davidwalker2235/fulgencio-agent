from __future__ import annotations

import asyncio
import base64
import json
import logging
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

from websockets.asyncio.client import ClientConnection, connect

from app.agent.prompts import instructions_for, tools_for
from app.agent.state_machine import ConversationStateMachine
from app.core.config import Settings


logger = logging.getLogger(__name__)


class LiteLLMRealtimeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._socket: ClientConnection | None = None
        self._send_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        model = quote(self._settings.model_name, safe="")
        url = f"{self._settings.litellm_proxy_ws_url}/v1/realtime?model={model}"
        headers = {
            "Authorization": f"Bearer {self._settings.litellm_proxy_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._socket = await connect(
            url,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._socket is not None:
            await self._socket.close()

    async def configure(
        self,
        machine: ConversationStateMachine,
        conversation_instructions: str | None = None,
    ) -> None:
        available_tools = tools_for(machine.state)
        await self.send_event(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": instructions_for(machine, conversation_instructions),
                    "voice": self._settings.realtime_voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                        # Server VAD is the sole owner of user-turn responses.
                        # LiteLLM 1.86.0 injects response.create when input
                        # transcription completes, so transcription is omitted
                        # to avoid a second response for the same audio turn.
                        "create_response": True,
                        "interrupt_response": True,
                    },
                    "tools": available_tools,
                    "tool_choice": "auto" if available_tools else "none",
                },
            }
        )

    async def append_audio(self, audio: bytes) -> None:
        await self.send_event(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio).decode("ascii"),
            }
        )

    async def send_tool_output(self, call_id: str, result: dict[str, Any]) -> None:
        await self.send_event(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                },
            }
        )

    async def create_response(self, instructions: str | None = None) -> None:
        logger.info("realtime_command type=response.create has_instructions=%s", bool(instructions))
        event: dict[str, Any] = {"type": "response.create"}
        if instructions:
            event["response"] = {
                "modalities": ["text", "audio"],
                "instructions": instructions,
            }
        await self.send_event(event)

    async def cancel_response(self) -> None:
        await self.send_event({"type": "response.cancel"})

    async def receive_event(self) -> dict[str, Any]:
        if self._socket is None:
            raise RuntimeError("La conexión Realtime no está abierta")
        raw = await self._socket.recv()
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                logger.error("LiteLLM envió un frame binario no UTF-8 (%d bytes)", len(raw))
                raise RuntimeError("LiteLLM ha enviado un evento binario no válido") from exc
        if not isinstance(raw, str):
            raise RuntimeError("LiteLLM ha enviado un evento no válido")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise RuntimeError("LiteLLM ha enviado un evento no válido")
        return event

    async def send_event(self, event: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError("La conexión Realtime no está abierta")
        async with self._send_lock:
            await self._socket.send(json.dumps(event, ensure_ascii=False))
