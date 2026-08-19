from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.domain.models import UserRecord


class PayloadTests(unittest.TestCase):
    def test_exact_caricature_payload(self) -> None:
        record = UserRecord(
            id=123,
            full_name="Ada Lovelace",
            email="ada@example.com",
            timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            real_name="Ada",
            work_name="Analytical Engine",
            request_id="req-1",
            caricature="base64",
            caricature_timestamp=None,
        )
        self.assertEqual(
            record.current_user_payload(),
            {
                "id": 123,
                "full_name": "Ada Lovelace",
                "email": "ada@example.com",
                "timestamp": "2026-01-02T00:00:00+00:00",
                "real_name": "Ada",
                "work_name": "Analytical Engine",
                "request_id": "req-1",
                "caricature": "base64",
                "caricature_timestamp": "",
            },
        )
        self.assertEqual(
            record.robot_action_payload(1234567890),
            {
                "type": "draw_caricature",
                "timestamp": 1234567890,
                "userId": 123,
                "fullName": "Ada Lovelace",
                "caricatureImage": "base64",
            },
        )

