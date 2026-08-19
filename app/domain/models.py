from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class ConversationState(str, Enum):
    OFFERING_OPTIONS = "offering_options"
    AWAITING_NUMBER = "awaiting_number"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    DRAWING = "drawing"
    FINISHED = "finished"


class Experience(str, Enum):
    CARICATURE = "caricature"
    GIFT = "gift"


def firebase_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    full_name: str
    email: str
    timestamp: Any
    real_name: Any = None
    work_name: Any = None
    request_id: Any = None
    caricature: Any = None
    caricature_timestamp: Any = None

    @property
    def has_caricature(self) -> bool:
        value = firebase_value(self.caricature)
        return isinstance(value, str) and bool(value.strip())

    def current_user_payload(self) -> dict[str, Any]:
        return {
            "id": int(self.id),
            "full_name": firebase_value(self.full_name),
            "email": firebase_value(self.email),
            "timestamp": firebase_value(self.timestamp),
            "real_name": firebase_value(self.real_name),
            "work_name": firebase_value(self.work_name),
            "request_id": firebase_value(self.request_id),
            "caricature": firebase_value(self.caricature),
            "caricature_timestamp": firebase_value(self.caricature_timestamp),
        }

    def robot_action_payload(self, action_timestamp: int) -> dict[str, Any]:
        return {
            "type": "draw_caricature",
            "timestamp": int(action_timestamp),
            "userId": int(self.id),
            "fullName": firebase_value(self.full_name),
            "caricatureImage": firebase_value(self.caricature),
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    name: str
    status: str
    message: str
    data: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.name,
            "status": self.status,
            "message": self.message,
        }
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass(frozen=True, slots=True)
class DrawingOutcome:
    status: str
    completed: bool
    message: str

