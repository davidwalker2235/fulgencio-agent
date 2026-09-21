from __future__ import annotations

import base64
import json
import struct
import unittest
from unittest.mock import AsyncMock, patch

from app.agent.state_machine import ConversationStateMachine
from app.core.config import Settings
from app.realtime.client import AzureRealtimeClient


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        return None


class ReceivingSocket:
    def __init__(self, message: bytes | str) -> None:
        self.message = message

    async def recv(self) -> bytes | str:
        return self.message


class RealtimeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_configures_audio_vad_and_function_tools(self) -> None:
        client = AzureRealtimeClient(Settings())
        socket = FakeSocket()
        client._socket = socket  # type: ignore[assignment]
        await client.configure(
            ConversationStateMachine(), "Habla solo sobre la exposición actual."
        )
        payload = json.loads(socket.messages[0])
        session = payload["session"]
        self.assertEqual(session["type"], "realtime")
        self.assertEqual(session["output_modalities"], ["audio"])
        self.assertEqual(
            session["audio"]["input"]["format"],
            {"type": "audio/pcm", "rate": 24_000},
        )
        self.assertEqual(
            session["audio"]["output"]["format"],
            {"type": "audio/pcm", "rate": 24_000},
        )
        turn_detection = session["audio"]["input"]["turn_detection"]
        self.assertEqual(turn_detection["type"], "server_vad")
        self.assertTrue(turn_detection["create_response"])
        self.assertNotIn("transcription", session["audio"]["input"])
        self.assertEqual(session["tools"][0]["name"], "choose_experience")
        self.assertIn("Habla solo sobre la exposición actual.", session["instructions"])
        self.assertIn("IMMUTABLE OPERATIONAL RULES", session["instructions"])

    async def test_audio_is_resampled_to_24khz_and_base64_encoded(self) -> None:
        client = AzureRealtimeClient(Settings())
        socket = FakeSocket()
        client._socket = socket  # type: ignore[assignment]
        await client.append_audio(b"\x00\x00" * 320)
        event = json.loads(socket.messages[0])
        self.assertEqual(event["type"], "input_audio_buffer.append")
        decoded = base64.b64decode(event["audio"])
        self.assertGreater(len(decoded), 640)
        self.assertEqual(len(decoded) % 2, 0)

    async def test_rejects_incomplete_pcm16_sample(self) -> None:
        client = AzureRealtimeClient(Settings())
        with self.assertRaises(ValueError):
            await client.append_audio(b"\x00")

    async def test_resampling_preserves_state_between_chunks(self) -> None:
        source = struct.pack("<320h", *range(-160, 160))

        chunked = AzureRealtimeClient(Settings())
        chunked_socket = FakeSocket()
        chunked._socket = chunked_socket  # type: ignore[assignment]
        await chunked.append_audio(source[:320])
        await chunked.append_audio(source[320:])
        chunked_audio = b"".join(
            base64.b64decode(json.loads(message)["audio"])
            for message in chunked_socket.messages
        )

        complete = AzureRealtimeClient(Settings())
        complete_socket = FakeSocket()
        complete._socket = complete_socket  # type: ignore[assignment]
        await complete.append_audio(source)
        complete_audio = base64.b64decode(
            json.loads(complete_socket.messages[0])["audio"]
        )

        self.assertEqual(chunked_audio, complete_audio)

    async def test_connects_to_azure_ga_endpoint_with_api_key(self) -> None:
        settings = Settings(
            azure_openai_endpoint="https://example.openai.azure.com/",
            azure_openai_deployment_name="realtime deployment",
            azure_openai_api_key="secret",
        )
        socket = FakeSocket()
        with patch(
            "app.realtime.client.connect", new=AsyncMock(return_value=socket)
        ) as connect_mock:
            async with AzureRealtimeClient(settings):
                pass

        args, kwargs = connect_mock.call_args
        self.assertEqual(
            args[0],
            "wss://example.openai.azure.com/openai/v1/realtime?model=realtime%20deployment",
        )
        self.assertEqual(kwargs["additional_headers"], {"api-key": "secret"})

    async def test_response_instructions_use_ga_output_modalities(self) -> None:
        client = AzureRealtimeClient(Settings())
        socket = FakeSocket()
        client._socket = socket  # type: ignore[assignment]
        await client.create_response("Say hello")
        self.assertEqual(
            json.loads(socket.messages[0]),
            {
                "type": "response.create",
                "response": {
                    "output_modalities": ["audio"],
                    "instructions": "Say hello",
                },
            },
        )

    async def test_binary_json_event_is_decoded(self) -> None:
        client = AzureRealtimeClient(Settings())
        client._socket = ReceivingSocket(b'{"type":"response.done"}')  # type: ignore[assignment]
        self.assertEqual(await client.receive_event(), {"type": "response.done"})
