from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError


MAX_CONVERSATION_INSTRUCTIONS_LENGTH = 16_000
CONVERSATION_CONFIG_QUERY_PARAM = "conversation_config"
CONVERSATION_CONFIG_MESSAGE_TYPE = "conversation.configure"


class ConversationConfigurationError(ValueError):
    """Raised when a consumer sends an invalid conversation configuration."""


class ConversationConfigureMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["conversation.configure"]
    instructions: str


def parse_conversation_configuration(payload: Any) -> str | None:
    try:
        message = ConversationConfigureMessage.model_validate(payload)
    except ValidationError as exc:
        raise ConversationConfigurationError(
            "La configuración de conversación no es válida"
        ) from exc

    instructions = message.instructions.strip()
    if not instructions:
        return None
    if len(instructions) > MAX_CONVERSATION_INSTRUCTIONS_LENGTH:
        raise ConversationConfigurationError(
            "Las instrucciones de conversación son demasiado largas"
        )
    return instructions
