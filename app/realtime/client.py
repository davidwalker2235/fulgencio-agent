from __future__ import annotations

import asyncio
import audioop
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


class AzureRealtimeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._socket: ClientConnection | None = None
        self._send_lock = asyncio.Lock()
        self._resample_state: tuple[int, tuple[int, ...]] | None = None

    async def __aenter__(self) -> Self:
        deployment = quote(self._settings.azure_openai_deployment_name, safe="")
        endpoint = self._settings.azure_openai_endpoint
        if endpoint.startswith("https://"):
            endpoint = "wss://" + endpoint.removeprefix("https://")
        elif endpoint.startswith("http://"):
            endpoint = "ws://" + endpoint.removeprefix("http://")
        url = f"{endpoint}/openai/v1/realtime?model={deployment}"
        headers = {"api-key": self._settings.azure_openai_api_key}
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
                    "type": "realtime",
                    "instructions": instructions_for(machine, conversation_instructions),
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24_000},
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
                                "create_response": True,
                                "interrupt_response": True,
                            },
                        },
                        "output": {
                            "format": {"type": "audio/pcm", "rate": 24_000},
                            "voice": self._settings.realtime_voice,
                        },
                    },
                    "tools": available_tools,
                    "tool_choice": "auto" if available_tools else "none",
                },
            }
        )

    async def append_audio(self, audio: bytes) -> None:
        if len(audio) % 2:
            raise ValueError("PCM16 audio chunks must contain complete 16-bit samples")
        audio, self._resample_state = audioop.ratecv(
            audio, 2, 1, 16_000, 24_000, self._resample_state
        )
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
                "output_modalities": ["audio"],
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
                logger.error("Azure Realtime envió un frame binario no UTF-8 (%d bytes)", len(raw))
                raise RuntimeError("Azure Realtime ha enviado un evento binario no válido") from exc
        if not isinstance(raw, str):
            raise RuntimeError("Azure Realtime ha enviado un evento no válido")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise RuntimeError("Azure Realtime ha enviado un evento no válido")
        return event

    async def send_event(self, event: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError("La conexión Realtime no está abierta")
        async with self._send_lock:
            await self._socket.send(json.dumps(event, ensure_ascii=False))
