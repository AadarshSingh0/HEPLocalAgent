"""Tests for conversational versus workflow routing."""

import unittest

from hep_agent.conversation import (
    ConversationRoute,
    answer_chat,
    classify_user_message,
)


class FailingIfCalledClient:
    def chat(self, **kwargs):
        raise AssertionError(
            "The model should not be called."
        )


class ConversationRoutingTests(
    unittest.TestCase
):
    def test_greeting_is_chat(self) -> None:
        self.assertEqual(
            classify_user_message("hi"),
            ConversationRoute.CHAT,
        )

    def test_capability_question_is_chat(
        self,
    ) -> None:
        self.assertEqual(
            classify_user_message(
                "What can you do?"
            ),
            ConversationRoute.CHAT,
        )

    def test_physics_question_is_chat(
        self,
    ) -> None:
        self.assertEqual(
            classify_user_message(
                "What is delta R and why is it useful?"
            ),
            ConversationRoute.CHAT,
        )

    def test_how_to_question_is_chat(
        self,
    ) -> None:
        self.assertEqual(
            classify_user_message(
                "How do I simulate pp collisions "
                "with MadGraph?"
            ),
            ConversationRoute.CHAT,
        )

    def test_explicit_simulation_is_workflow(
        self,
    ) -> None:
        self.assertEqual(
            classify_user_message(
                "Simulate proton-proton collisions "
                "producing e+ e- at 13 TeV with "
                "100 events."
            ),
            ConversationRoute.WORKFLOW,
        )

    def test_software_command_is_workflow(
        self,
    ) -> None:
        self.assertEqual(
            classify_user_message(
                "Run MadGraph and Pythia8 for "
                "pp > mu+ mu-."
            ),
            ConversationRoute.WORKFLOW,
        )

    def test_compact_process_is_workflow(
        self,
    ) -> None:
        self.assertEqual(
            classify_user_message(
                "pp > e+ e- at 13 TeV, 200 events"
            ),
            ConversationRoute.WORKFLOW,
        )

    def test_greeting_does_not_call_model(
        self,
    ) -> None:
        answer = answer_chat(
            "hello",
            client=FailingIfCalledClient(),
        )

        self.assertIsNone(
            answer.model
        )
        self.assertIn(
            "particle-physics",
            answer.content,
        )


if __name__ == "__main__":
    unittest.main()
