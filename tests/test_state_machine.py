from __future__ import annotations

import unittest

from app.agent.state_machine import ConversationStateMachine
from app.domain.errors import InvalidTransitionError
from app.domain.models import ConversationState, Experience


class StateMachineTests(unittest.TestCase):
    def test_caricature_positive_flow(self) -> None:
        machine = ConversationStateMachine()
        machine.choose_experience(Experience.CARICATURE)
        machine.capture_number(123)
        machine.start_drawing()
        machine.finish_drawing()
        self.assertEqual(machine.state, ConversationState.FINISHED)
        self.assertTrue(machine.action_published)

    def test_negative_confirmation_clears_number(self) -> None:
        machine = ConversationStateMachine()
        machine.choose_experience(Experience.CARICATURE)
        machine.capture_number(123)
        machine.reject_number()
        self.assertEqual(machine.state, ConversationState.AWAITING_NUMBER)
        self.assertIsNone(machine.pending_number)

    def test_invalid_transition_is_rejected(self) -> None:
        machine = ConversationStateMachine()
        with self.assertRaises(InvalidTransitionError):
            machine.capture_number(12)

    def test_call_ids_are_idempotent(self) -> None:
        machine = ConversationStateMachine()
        self.assertTrue(machine.register_call("call-1"))
        self.assertFalse(machine.register_call("call-1"))

