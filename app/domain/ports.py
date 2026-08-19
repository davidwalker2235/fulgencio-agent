from __future__ import annotations

from typing import Protocol

from app.domain.models import DrawingOutcome, UserRecord


class UserRepository(Protocol):
    async def get_by_id(self, user_id: int) -> UserRecord | None: ...


class RobotGateway(Protocol):
    async def get_status(self) -> str: ...

    async def publish_caricature(self, user: UserRecord) -> None: ...

    async def publish_gift(self) -> None: ...

    async def wait_for_drawing_completion(self) -> DrawingOutcome: ...

