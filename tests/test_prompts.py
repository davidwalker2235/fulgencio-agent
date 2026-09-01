from __future__ import annotations

import unittest

from app.agent.prompts import (
    DEFAULT_CONVERSATION_INSTRUCTIONS,
    IMMUTABLE_INSTRUCTIONS,
    instructions_for,
    tools_for,
)
from app.agent.state_machine import ConversationStateMachine


class PromptCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = ConversationStateMachine()

    def test_default_conversation_preserves_current_behavior(self) -> None:
        instructions = instructions_for(self.machine)

        self.assertIn(DEFAULT_CONVERSATION_INSTRUCTIONS, instructions)
        self.assertIn(IMMUTABLE_INSTRUCTIONS, instructions)
        self.assertIn("hacer una caricatura", instructions)
        self.assertIn("bolsa de regalo", instructions)

    def test_custom_conversation_replaces_only_conversation_layer(self) -> None:
        custom = "Eres una guía de museo. Limita la charla a la exposición actual."

        instructions = instructions_for(self.machine, custom)

        self.assertIn(custom, instructions)
        self.assertNotIn(DEFAULT_CONVERSATION_INSTRUCTIONS, instructions)
        self.assertIn(IMMUTABLE_INSTRUCTIONS, instructions)
        self.assertIn("ESTADO OPERATIVO ACTUAL: offering_options", instructions)
        self.assertEqual(tools_for(self.machine.state)[0]["name"], "choose_experience")

    def test_blank_custom_conversation_uses_default(self) -> None:
        self.assertIn(DEFAULT_CONVERSATION_INSTRUCTIONS, instructions_for(self.machine, "  "))


if __name__ == "__main__":
    unittest.main()
