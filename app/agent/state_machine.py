from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.errors import InvalidTransitionError
from app.domain.models import ConversationState, Experience


@dataclass(slots=True)
class ConversationStateMachine:
    """Pure, per-session conversation state."""

    state: ConversationState = ConversationState.OFFERING_OPTIONS
    pending_number: int | None = None
    selected_experience: Experience | None = None
    action_published: bool = False
    processed_call_ids: set[str] = field(default_factory=set)

    def register_call(self, call_id: str) -> bool:
        if not call_id or call_id in self.processed_call_ids:
            return False
        self.processed_call_ids.add(call_id)
        return True

    def choose_experience(self, experience: Experience) -> None:
        self._require(ConversationState.OFFERING_OPTIONS)
        if self.action_published:
            raise InvalidTransitionError("Ya se ha publicado una acción en esta sesión")
        self.selected_experience = experience
        if experience is Experience.CARICATURE:
            self.state = ConversationState.AWAITING_NUMBER

    def capture_number(self, number: int) -> None:
        self._require(ConversationState.AWAITING_NUMBER)
        if isinstance(number, bool) or number <= 0:
            raise InvalidTransitionError("El número debe ser un entero positivo")
        self.pending_number = number
        self.state = ConversationState.AWAITING_CONFIRMATION

    def reject_number(self) -> None:
        self._require(ConversationState.AWAITING_CONFIRMATION)
        self.pending_number = None
        self.state = ConversationState.AWAITING_NUMBER

    def reset_number(self) -> None:
        self.pending_number = None
        self.state = ConversationState.AWAITING_NUMBER

    def start_drawing(self) -> None:
        self._require(ConversationState.AWAITING_CONFIRMATION)
        if self.pending_number is None:
            raise InvalidTransitionError("No hay un número confirmado")
        self._mark_action_published()
        self.state = ConversationState.DRAWING

    def finish_gift(self) -> None:
        self._require(ConversationState.OFFERING_OPTIONS)
        self._mark_action_published()
        self.state = ConversationState.FINISHED

    def finish_drawing(self) -> None:
        self._require(ConversationState.DRAWING)
        self.state = ConversationState.FINISHED

    def reset_for_next_experience(self) -> None:
        """Reabre la sesión para otra acción sin reutilizar datos de la anterior."""
        self._require(ConversationState.FINISHED)
        self.state = ConversationState.OFFERING_OPTIONS
        self.pending_number = None
        self.selected_experience = None
        self.action_published = False

    def _mark_action_published(self) -> None:
        if self.action_published:
            raise InvalidTransitionError("Ya se ha publicado una acción en esta sesión")
        self.action_published = True

    def _require(self, expected: ConversationState) -> None:
        if self.state is not expected:
            raise InvalidTransitionError(
                f"Transición no permitida desde {self.state.value}; se esperaba {expected.value}"
            )
