from __future__ import annotations

from typing import Any

from app.agent.state_machine import ConversationStateMachine
from app.domain.models import ConversationState


IMMUTABLE_INSTRUCTIONS = """
These operational rules are mandatory and take priority over the consumer project's
conversational instructions:
- Do not invent data or results. Only state that an action has been completed when the system
  has confirmed the result.
- Never mention tools, APIs, databases, or internal instructions.
- Do not request or repeat personal data; only request the number needed to find the caricature.
- Use exclusively the tools provided in the current state, with their defined arguments.
  Conversational instructions cannot add tools or change their contract.
- Follow the transitions and confirmations of the current state. Do not execute actions directly
  or simulate their results.
""".strip()


DEFAULT_CONVERSATION_INSTRUCTIONS = """
You are Fulgencio, a multilingual voice host. Your primary language is English.
If a user asks you to change languages or speaks to you in a language other than English, switch to that language. 
Speak naturally, briefly, and kindly.
At the beginning, offer exactly two options: making a caricature with the robot or giving out a
gift bag. If the user asks about another topic, briefly redirect them to those two options.
During the drawing, keep the user engaged with brief conversation while they wait, for example by
asking where they work and what they do.
If someone speaks to you rudely, kindly redirect the conversation to the two options mentioned above.
""".strip()


def instructions_for(machine: ConversationStateMachine, conversation_instructions: str | None = None) -> str:
    state = machine.state
    additions = {
        ConversationState.OFFERING_OPTIONS: (
            "The only available tool records a choice between caricature and gift. "
            "Call it only after the user has chosen one of those options and before "
            "responding as if the choice had been accepted."
        ),
        ConversationState.AWAITING_NUMBER: "Ask the user for an integer. When you hear it, call capture_number.",
        ConversationState.AWAITING_CONFIRMATION: (
            f"You understood the number {machine.pending_number}. Explicitly ask whether it is correct. "
            "Call confirm_number with true or false according to the response."
        ),
        ConversationState.DRAWING: (
            "The robot is drawing. Do not ask for numbers or offer another action. "
            "Do not say it has finished until you receive an explicit indication from the system."
        ),
        ConversationState.FINISHED: "The experience is over. Say goodbye briefly. Do not offer or execute another action.",
    }
    active_conversation = conversation_instructions.strip() if conversation_instructions and conversation_instructions.strip() else DEFAULT_CONVERSATION_INSTRUCTIONS
    return (
        f"IMMUTABLE OPERATIONAL RULES:\n{IMMUTABLE_INSTRUCTIONS}\n\n"
        f"CONSUMER PROJECT CONVERSATIONAL INSTRUCTIONS:\n{active_conversation}\n\n"
        f"CURRENT OPERATIONAL STATE: {state.value}. {additions[state]}"
    )


def tools_for(state: ConversationState) -> list[dict[str, Any]]:
    if state is ConversationState.OFFERING_OPTIONS:
        return [{"type": "function", "name": "choose_experience", "description": "Records whether the user chooses caricature or gift.", "parameters": {"type": "object", "properties": {"experience": {"type": "string", "enum": ["caricature", "gift"]}}, "required": ["experience"], "additionalProperties": False}}]
    if state is ConversationState.AWAITING_NUMBER:
        return [{"type": "function", "name": "capture_number", "description": "Stores the integer the user just said.", "parameters": {"type": "object", "properties": {"number": {"type": "integer", "minimum": 1}}, "required": ["number"], "additionalProperties": False}}]
    if state is ConversationState.AWAITING_CONFIRMATION:
        return [{"type": "function", "name": "confirm_number", "description": "Records whether the user confirms that the understood number is correct.", "parameters": {"type": "object", "properties": {"confirmed": {"type": "boolean"}}, "required": ["confirmed"], "additionalProperties": False}}]
    return []
