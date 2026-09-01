from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FunctionCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


def parse_function_call(event: dict[str, Any]) -> FunctionCall | None:
    event_type = event.get("type")
    if event_type == "response.function_call_arguments.done":
        return _build_call(
            event.get("call_id"), event.get("name"), event.get("arguments", "{}")
        )
    if event_type == "response.output_item.done":
        item = event.get("item") or {}
        if item.get("type") == "function_call":
            return _build_call(
                item.get("call_id"), item.get("name"), item.get("arguments", "{}")
            )
    return None


def _build_call(call_id: Any, name: Any, raw_arguments: Any) -> FunctionCall | None:
    if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
        return None
    try:
        arguments = (
            json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        )
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return FunctionCall(call_id, name, arguments)


def to_frontend_events(
    event: dict[str, Any], *, include_agent_end: bool = True
) -> list[dict[str, Any]]:
    """Convert Realtime events to the established Erni frontend contract."""
    event_type = str(event.get("type", ""))
    if event_type == "conversation.item.input_audio_transcription.delta":
        return [{"type": "stt_chunk", "transcript": event.get("delta", "")}]
    if event_type == "conversation.item.input_audio_transcription.completed":
        return [{"type": "stt_output", "transcript": event.get("transcript", "")}]
    if event_type in {
        "response.audio_transcript.delta",
        "response.output_audio_transcript.delta",
        "response.text.delta",
        "response.output_text.delta",
    }:
        return [{"type": "agent_chunk", "text": event.get("delta", "")}]
    if event_type in {"response.audio.delta", "response.output_audio.delta"}:
        return [{"type": "tts_chunk", "audio": event.get("delta", "")}]
    if event_type == "response.done":
        return [{"type": "agent_end"}] if include_agent_end else []
    if event_type == "error":
        error = event.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        return [{"type": "error", "message": message or "Error del servicio Realtime"}]
    return []
