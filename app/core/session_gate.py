from __future__ import annotations

import asyncio


class SingleSessionGate:
    """Allows exactly one active voice session in a process."""

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._active = False

    async def try_acquire(self) -> bool:
        async with self._guard:
            if self._active:
                return False
            self._active = True
            return True

    async def release(self) -> None:
        async with self._guard:
            self._active = False

    async def is_active(self) -> bool:
        async with self._guard:
            return self._active

