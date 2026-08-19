from __future__ import annotations

import unittest

from app.realtime.protocol import parse_function_call, to_frontend_events


class ProtocolTests(unittest.TestCase):
    def test_maps_audio_text_and_transcription_events(self) -> None:
        cases = [
            (
                {"type": "conversation.item.input_audio_transcription.delta", "delta": "ho"},
                {"type": "stt_chunk", "transcript": "ho"},
            ),
            (
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "hola",
                },
                {"type": "stt_output", "transcript": "hola"},
            ),
            (
                {"type": "response.audio_transcript.delta", "delta": "Hola"},
                {"type": "agent_chunk", "text": "Hola"},
            ),
            (
                {"type": "response.audio.delta", "delta": "AAEC"},
                {"type": "tts_chunk", "audio": "AAEC"},
            ),
            ({"type": "response.done"}, {"type": "agent_end"}),
        ]
        for source, expected in cases:
            with self.subTest(source=source["type"]):
                self.assertEqual(to_frontend_events(source), [expected])

    def test_parses_function_call_formats(self) -> None:
        direct = parse_function_call(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call-1",
                "name": "capture_number",
                "arguments": '{"number": 42}',
            }
        )
        item = parse_function_call(
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "call_id": "call-2",
                    "name": "confirm_number",
                    "arguments": '{"confirmed": true}',
                },
            }
        )
        self.assertEqual(direct.arguments, {"number": 42})  # type: ignore[union-attr]
        self.assertEqual(item.arguments, {"confirmed": True})  # type: ignore[union-attr]

