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
        machine.reset_for_next_experience()
        self.assertEqual(machine.state, ConversationState.OFFERING_OPTIONS)
        self.assertFalse(machine.action_published)
        self.assertIsNone(machine.pending_number)
        machine.choose_experience(Experience.CARICATURE)
        machine.capture_number(456)
        machine.start_drawing()
        self.assertEqual(machine.state, ConversationState.DRAWING)

    def test_negative_confirmation_clears_number(self) -> None:
        machine = ConversationStateMachine()
        machine.choose_experience(Experience.CARICATURE)
        machine.capture_number(123)
        machine.reject_number()
        self.assertEqual(machine.state, ConversationState.AWAITING_NUMBER)
        self.assertIsNone(machine.pending_number)

    def test_gift_can_be_requested_again_after_reset(self) -> None:
        machine = ConversationStateMachine()
        machine.choose_experience(Experience.GIFT)
        machine.finish_gift()
        machine.reset_for_next_experience()
        machine.choose_experience(Experience.GIFT)
        machine.finish_gift()
        self.assertEqual(machine.state, ConversationState.FINISHED)

    def test_invalid_transition_is_rejected(self) -> None:
        machine = ConversationStateMachine()
        with self.assertRaises(InvalidTransitionError):
            machine.capture_number(12)

    def test_call_ids_are_idempotent(self) -> None:
        machine = ConversationStateMachine()
        self.assertTrue(machine.register_call("call-1"))
        self.assertFalse(machine.register_call("call-1"))
