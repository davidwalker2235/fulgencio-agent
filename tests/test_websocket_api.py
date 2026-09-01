from __future__ import annotations

import asyncio
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import router
from app.core.session_gate import SingleSessionGate


class FakeContainer:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            ws_basic_username="user",
            ws_basic_password="pass",
            ws_basic_auth_required=True,
        )
        self.session_gate = SingleSessionGate()
        self.conversation_instructions: list[str | None] = []

    def create_voice_session(self, conversation_instructions: str | None = None):
        self.conversation_instructions.append(conversation_instructions)

        class FakeSession:
            async def run(inner_self, websocket) -> None:
                await websocket.send_json({"type": "test.session.completed"})

        return FakeSession()


class WebSocketApiTests(unittest.TestCase):
    def app(self, container: FakeContainer) -> FastAPI:
        app = FastAPI()
        app.state.container = container
        app.include_router(router)
        return app

    def test_rejects_missing_basic_auth(self) -> None:
        with TestClient(self.app(FakeContainer())) as client:
            with self.assertRaises(WebSocketDisconnect) as context:
                with client.websocket_connect("/ws"):
                    pass
        self.assertEqual(context.exception.code, 1008)

    def test_rejects_second_session_as_busy(self) -> None:
        container = FakeContainer()
        asyncio.run(container.session_gate.try_acquire())
        token = base64.b64encode(b"user:pass").decode("ascii")
        with TestClient(self.app(container)) as client:
            with client.websocket_connect(
                "/ws", headers={"Authorization": f"Basic {token}"}
            ) as websocket:
                self.assertEqual(
                    websocket.receive_json(),
                    {"type": "error", "message": "El agente está ocupado"},
                )

    def test_applies_custom_conversation_before_creating_session(self) -> None:
        container = FakeContainer()
        token = base64.b64encode(b"user:pass").decode("ascii")
        with TestClient(self.app(container)) as client:
            with client.websocket_connect(
                "/ws?conversation_config=1",
                headers={"Authorization": f"Basic {token}"},
            ) as websocket:
                websocket.send_json(
                    {
                        "type": "conversation.configure",
                        "instructions": "  Habla como guía de museo.  ",
                    }
                )
                self.assertEqual(
                    websocket.receive_json(), {"type": "test.session.completed"}
                )
        self.assertEqual(container.conversation_instructions, ["Habla como guía de museo."])

    def test_uses_default_conversation_without_configuration_flag(self) -> None:
        container = FakeContainer()
        token = base64.b64encode(b"user:pass").decode("ascii")
        with TestClient(self.app(container)) as client:
            with client.websocket_connect(
                "/ws", headers={"Authorization": f"Basic {token}"}
            ) as websocket:
                self.assertEqual(
                    websocket.receive_json(), {"type": "test.session.completed"}
                )
        self.assertEqual(container.conversation_instructions, [None])

    def test_empty_custom_conversation_uses_default(self) -> None:
        container = FakeContainer()
        token = base64.b64encode(b"user:pass").decode("ascii")
        with TestClient(self.app(container)) as client:
            with client.websocket_connect(
                "/ws?conversation_config=1",
                headers={"Authorization": f"Basic {token}"},
            ) as websocket:
                websocket.send_json(
                    {"type": "conversation.configure", "instructions": "   "}
                )
                self.assertEqual(
                    websocket.receive_json(), {"type": "test.session.completed"}
                )
        self.assertEqual(container.conversation_instructions, [None])

    def test_rejects_oversized_custom_conversation(self) -> None:
        container = FakeContainer()
        token = base64.b64encode(b"user:pass").decode("ascii")
        with TestClient(self.app(container)) as client:
            with client.websocket_connect(
                "/ws?conversation_config=1",
                headers={"Authorization": f"Basic {token}"},
            ) as websocket:
                websocket.send_json(
                    {"type": "conversation.configure", "instructions": "x" * 16_001}
                )
                self.assertEqual(
                    websocket.receive_json(),
                    {
                        "type": "error",
                        "message": "Las instrucciones de conversación son demasiado largas",
                    },
                )
                with self.assertRaises(WebSocketDisconnect) as context:
                    websocket.receive_json()
        self.assertEqual(context.exception.code, 1008)
        self.assertEqual(container.conversation_instructions, [])

    def test_rejects_malformed_custom_conversation(self) -> None:
        container = FakeContainer()
        token = base64.b64encode(b"user:pass").decode("ascii")
        with TestClient(self.app(container)) as client:
            with client.websocket_connect(
                "/ws?conversation_config=1",
                headers={"Authorization": f"Basic {token}"},
            ) as websocket:
                websocket.send_json(
                    {"type": "conversation.configure", "instructions": 123}
                )
                self.assertEqual(
                    websocket.receive_json(),
                    {
                        "type": "error",
                        "message": "La configuración de conversación no es válida",
                    },
                )
        self.assertEqual(container.conversation_instructions, [])

    def test_rejects_missing_initial_configuration_message(self) -> None:
        container = FakeContainer()
        token = base64.b64encode(b"user:pass").decode("ascii")
        with patch(
            "app.api.websocket.CONVERSATION_CONFIG_TIMEOUT_SECONDS", 0.01
        ):
            with TestClient(self.app(container)) as client:
                with client.websocket_connect(
                    "/ws?conversation_config=1",
                    headers={"Authorization": f"Basic {token}"},
                ) as websocket:
                    self.assertEqual(
                        websocket.receive_json(),
                        {
                            "type": "error",
                            "message": "No se recibió la configuración de conversación",
                        },
                    )
        self.assertEqual(container.conversation_instructions, [])
