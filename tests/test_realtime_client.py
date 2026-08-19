from __future__ import annotations

import json
import unittest

from app.agent.state_machine import ConversationStateMachine
from app.core.config import Settings
from app.realtime.client import LiteLLMRealtimeClient


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


class RealtimeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_configures_audio_vad_and_function_tools(self) -> None:
        client = LiteLLMRealtimeClient(Settings())
        socket = FakeSocket()
        client._socket = socket  # type: ignore[assignment]
        await client.configure(ConversationStateMachine())
        payload = json.loads(socket.messages[0])
        session = payload["session"]
        self.assertEqual(session["input_audio_format"], "pcm16")
        self.assertEqual(session["output_audio_format"], "pcm16")
        self.assertEqual(session["turn_detection"]["type"], "server_vad")
        self.assertEqual(session["tools"][0]["name"], "choose_experience")

    async def test_audio_is_base64_encoded(self) -> None:
        client = LiteLLMRealtimeClient(Settings())
        socket = FakeSocket()
        client._socket = socket  # type: ignore[assignment]
        await client.append_audio(b"\x00\x01")
        self.assertEqual(
            json.loads(socket.messages[0]),
            {"type": "input_audio_buffer.append", "audio": "AAE="},
        )

