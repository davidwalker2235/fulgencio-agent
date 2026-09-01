from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock

from app.agent.session import VoiceSession
from app.core.config import Settings
from app.domain.models import DrawingOutcome, Experience


class FakeUsers:
    async def get_by_id(self, user_id: int) -> None:
        return None


class FakeRobot:
    async def get_status(self) -> str:
        return "idle"

    async def publish_gift(self) -> None:
        return None

    async def publish_caricature(self, user: Any) -> None:
        return None

    async def wait_for_drawing_completion(
        self, *, on_start_timeout=None, on_late_start=None
    ) -> DrawingOutcome:
        return DrawingOutcome("idle", True, "done")


class FakeFrontend:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.messages.append(payload)

    async def receive(self) -> dict[str, str]:
        return {"type": "websocket.disconnect"}


class FakeRealtime:
    def __init__(self) -> None:
        self.events = [
            {"type": "response.created"},
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call-1",
                "name": "choose_experience",
                "arguments": '{"experience":"caricature"}',
            },
            {"type": "response.done"},
        ]
        self.response_done_seen = False
        self.response_create_after_done: list[bool] = []
        self.followup_created = asyncio.Event()
        self.configured_conversations: list[str | None] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def receive_event(self) -> dict[str, Any]:
        if self.events:
            event = self.events.pop(0)
            if event["type"] == "response.done":
                self.response_done_seen = True
            return event
        await asyncio.Future()
        raise AssertionError("unreachable")

    async def send_tool_output(self, call_id: str, result: dict[str, Any]) -> None:
        return None

    async def configure(
        self, machine: Any, conversation_instructions: str | None = None
    ) -> None:
        self.configured_conversations.append(conversation_instructions)

    async def create_response(self, instructions: str | None = None) -> None:
        self.response_create_after_done.append(self.response_done_seen)
        self.followup_created.set()


class VoiceSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_start_announcements_are_only_sent_in_observation_mode(self) -> None:
        session = VoiceSession(Settings(), FakeUsers(), FakeRobot())  # type: ignore[arg-type]
        session._request_response = AsyncMock()  # type: ignore[method-assign]
        realtime = object()

        await session._handle_late_drawing_start(realtime)  # type: ignore[arg-type]
        session._machine.choose_experience(Experience.CARICATURE)
        session._machine.capture_number(1)
        session._machine.start_drawing()
        await session._handle_drawing_start_timeout(realtime)  # type: ignore[arg-type]
        await session._handle_late_drawing_start(realtime)  # type: ignore[arg-type]
        await session._handle_late_drawing_start(realtime)  # type: ignore[arg-type]

        self.assertEqual(session._request_response.await_count, 2)  # type: ignore[attr-defined]
        warning = session._request_response.await_args_list[0].args[1]  # type: ignore[attr-defined]
        late = session._request_response.await_args_list[1].args[1]  # type: ignore[attr-defined]
        self.assertIn("todavía no ha empezado", warning)
        self.assertIn("ya está dibujando", late)

    async def test_custom_conversation_is_configured_before_initial_greeting(self) -> None:
        realtime = FakeRealtime()
        realtime.events = []
        session = VoiceSession(
            Settings(),
            FakeUsers(),
            FakeRobot(),
            realtime_factory=lambda settings: realtime,
            conversation_instructions="Conversación personalizada",
        )  # type: ignore[arg-type]
        frontend = FakeFrontend()

        await session.run(frontend)  # type: ignore[arg-type]

        self.assertEqual(
            realtime.configured_conversations, ["Conversación personalizada"]
        )
        self.assertEqual(realtime.response_create_after_done, [False])
        self.assertEqual(frontend.messages[0]["type"], "session.created")

    async def test_tool_followup_waits_for_response_done(self) -> None:
        session = VoiceSession(
            Settings(),
            FakeUsers(),
            FakeRobot(),
            conversation_instructions="Conversación personalizada",
        )  # type: ignore[arg-type]
        frontend = FakeFrontend()
        realtime = FakeRealtime()

        task = asyncio.create_task(
            session._receive_realtime(frontend, realtime)  # type: ignore[arg-type]
        )
        await asyncio.wait_for(realtime.followup_created.wait(), timeout=1)

        self.assertEqual(realtime.response_create_after_done, [True])
        self.assertEqual(
            realtime.configured_conversations, ["Conversación personalizada"]
        )
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_committed_audio_does_not_create_manual_response(self) -> None:
        session = VoiceSession(Settings(), FakeUsers(), FakeRobot())  # type: ignore[arg-type]
        frontend = FakeFrontend()
        realtime = FakeRealtime()
        realtime.events = [
            {"type": "response.created"},
            {"type": "input_audio_buffer.committed"},
            {"type": "input_audio_buffer.committed"},
            {"type": "response.done"},
        ]

        task = asyncio.create_task(
            session._receive_realtime(frontend, realtime)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0)

        self.assertEqual(realtime.response_create_after_done, [])
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_response_done_still_starts_pending_tool_followup(self) -> None:
        session = VoiceSession(Settings(), FakeUsers(), FakeRobot())  # type: ignore[arg-type]
        frontend = FakeFrontend()
        realtime = FakeRealtime()
        realtime.events = [
            {"type": "response.created"},
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call-1",
                "name": "choose_experience",
                "arguments": '{"experience":"caricature"}',
            },
            {"type": "response.done"},
        ]

        task = asyncio.create_task(
            session._receive_realtime(frontend, realtime)  # type: ignore[arg-type]
        )
        await asyncio.wait_for(realtime.followup_created.wait(), timeout=1)

        self.assertEqual(realtime.response_create_after_done, [True])
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    unittest.main()
