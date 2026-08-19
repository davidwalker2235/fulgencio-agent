from __future__ import annotations

import base64
import unittest

from app.core.security import validate_basic_authorization
from app.core.session_gate import SingleSessionGate


class SecurityTests(unittest.TestCase):
    def test_basic_auth(self) -> None:
        token = base64.b64encode(b"user:pass").decode("ascii")
        self.assertTrue(
            validate_basic_authorization({"authorization": f"Basic {token}"}, "user", "pass")
        )
        self.assertFalse(
            validate_basic_authorization({"authorization": f"Basic {token}"}, "user", "bad")
        )


class GateTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_one_session_is_active(self) -> None:
        gate = SingleSessionGate()
        self.assertTrue(await gate.try_acquire())
        self.assertFalse(await gate.try_acquire())
        await gate.release()
        self.assertTrue(await gate.try_acquire())

