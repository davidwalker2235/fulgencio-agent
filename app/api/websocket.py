from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.container import AppContainer
from app.core.security import validate_basic_authorization
from app.domain.conversation import (
    CONVERSATION_CONFIG_QUERY_PARAM,
    ConversationConfigurationError,
    parse_conversation_configuration,
)

logger = logging.getLogger(__name__)
router = APIRouter()
CONVERSATION_CONFIG_TIMEOUT_SECONDS = 5.0


async def _receive_conversation_instructions(websocket: WebSocket) -> str | None:
    if websocket.query_params.get(CONVERSATION_CONFIG_QUERY_PARAM) != "1":
        return None
    try:
        payload = await asyncio.wait_for(
            websocket.receive_json(), timeout=CONVERSATION_CONFIG_TIMEOUT_SECONDS
        )
    except TimeoutError as exc:
        raise ConversationConfigurationError(
            "No se recibió la configuración de conversación"
        ) from exc
    except WebSocketDisconnect:
        raise
    except (RuntimeError, ValueError) as exc:
        raise ConversationConfigurationError(
            "La configuración de conversación no es válida"
        ) from exc
    return parse_conversation_configuration(payload)


@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket) -> None:
    container: AppContainer = websocket.app.state.container
    settings = container.settings
    if settings.ws_basic_auth_required and not validate_basic_authorization(
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
        try:
            conversation_instructions = await _receive_conversation_instructions(
                websocket
            )
        except ConversationConfigurationError as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1008, reason="Configuración no válida")
            return
        except WebSocketDisconnect:
            return
        await container.create_voice_session(conversation_instructions).run(websocket)
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
