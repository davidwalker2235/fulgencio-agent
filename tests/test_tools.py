from __future__ import annotations

import unittest

from app.agent.state_machine import ConversationStateMachine
from app.agent.tools import ToolExecutor
from app.domain.models import ConversationState, DrawingOutcome, UserRecord


class FakeUsers:
    def __init__(self, user: UserRecord | None) -> None:
        self.user = user
        self.lookups: list[int] = []

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        self.lookups.append(user_id)
        return self.user


class FakeRobot:
    def __init__(self, status: str = "idle") -> None:
        self.status = status
        self.gifts = 0
        self.caricatures: list[UserRecord] = []

    async def get_status(self) -> str:
        return self.status

    async def publish_gift(self) -> None:
        self.gifts += 1

    async def publish_caricature(self, user: UserRecord) -> None:
        self.caricatures.append(user)

    async def wait_for_drawing_completion(
        self, *, on_start_timeout=None, on_late_start=None
    ) -> DrawingOutcome:
        return DrawingOutcome("idle", True, "done")


def user(caricature: str = "base64-image") -> UserRecord:
    return UserRecord(12, "Ada", "ada@example.com", "2026-01-01", caricature=caricature)


class ToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_azure_lookup_before_positive_confirmation(self) -> None:
        users = FakeUsers(user())
        tools = ToolExecutor(ConversationStateMachine(), users, FakeRobot())
        await tools.execute("1", "choose_experience", {"experience": "caricature"})
        await tools.execute("2", "capture_number", {"number": 12})
        self.assertEqual(users.lookups, [])
        await tools.execute("3", "confirm_number", {"confirmed": False})
        self.assertEqual(users.lookups, [])

    async def test_confirmed_caricature_is_published_once(self) -> None:
        machine = ConversationStateMachine()
        users = FakeUsers(user())
        robot = FakeRobot()
        tools = ToolExecutor(machine, users, robot)
        await tools.execute("1", "choose_experience", {"experience": "caricature"})
        await tools.execute("2", "capture_number", {"number": 12})
        result = await tools.execute("3", "confirm_number", {"confirmed": True})
        duplicate = await tools.execute("3", "confirm_number", {"confirmed": True})
        self.assertEqual(result.status, "ok")
        self.assertEqual(duplicate, result)
        self.assertEqual(len(robot.caricatures), 1)
        self.assertEqual(machine.state, ConversationState.DRAWING)

    async def test_missing_caricature_is_not_published(self) -> None:
        machine = ConversationStateMachine()
        robot = FakeRobot()
        tools = ToolExecutor(machine, FakeUsers(user("")), robot)
        await tools.execute("1", "choose_experience", {"experience": "caricature"})
        await tools.execute("2", "capture_number", {"number": 12})
        result = await tools.execute("3", "confirm_number", {"confirmed": True})
        self.assertEqual(result.status, "not_found")
        self.assertEqual(robot.caricatures, [])
        self.assertEqual(machine.state, ConversationState.AWAITING_NUMBER)

    async def test_missing_user_is_not_published(self) -> None:
        machine = ConversationStateMachine()
        robot = FakeRobot()
        tools = ToolExecutor(machine, FakeUsers(None), robot)
        await tools.execute("1", "choose_experience", {"experience": "caricature"})
        await tools.execute("2", "capture_number", {"number": 99})
        result = await tools.execute("3", "confirm_number", {"confirmed": True})
        self.assertEqual(result.status, "not_found")
        self.assertEqual(robot.caricatures, [])

    async def test_busy_robot_rejects_gift(self) -> None:
        machine = ConversationStateMachine()
        robot = FakeRobot("drawing")
        result = await ToolExecutor(machine, FakeUsers(None), robot).execute(
            "1", "choose_experience", {"experience": "gift"}
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(robot.gifts, 0)
        self.assertFalse(machine.action_published)
