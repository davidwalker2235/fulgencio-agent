from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

from app.core.container import AppContainer
from app.core.security import validate_basic_authorization

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket) -> None:
    container: AppContainer = websocket.app.state.container
    settings = container.settings
    if not validate_basic_authorization(
        websocket.headers, settings.ws_basic_username, settings.ws_basic_password
    ):
        await websocket.close(code=1008, reason="No autorizado")
        return
    if not await container.session_gate.try_acquire():
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "El agente está ocupado"})
        await websocket.close(code=1013, reason="Agente ocupado")
        return

    await websocket.accept()
    try:
        await container.create_voice_session().run(websocket)
    except Exception:
        logger.exception("Voice session failed")
        try:
            await websocket.send_json(
                {"type": "error", "message": "La sesión de voz ha fallado"}
            )
        except RuntimeError:
            pass
    finally:
        await container.session_gate.release()
        try:
            await websocket.close()
        except RuntimeError:
            pass
