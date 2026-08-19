from __future__ import annotations

import asyncio
import base64
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.websocket import router
from app.core.session_gate import SingleSessionGate


class FakeContainer:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(ws_basic_username="user", ws_basic_password="pass")
        self.session_gate = SingleSessionGate()

    def create_voice_session(self):
        raise AssertionError("No debe crearse una sesión en estos casos")


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

