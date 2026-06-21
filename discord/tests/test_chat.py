import unittest
from types import SimpleNamespace

from bot.chat import (
    ChatError,
    _session_key,
    build_fallback_reply,
    build_model_prompt,
    response_needs_continuation,
)
from bot.search import SearchResult


class ChatTest(unittest.TestCase):
    def test_session_key_is_channel_only(self):
        self.assertEqual(_session_key(123), 123)

    def test_build_model_prompt_includes_speaker_and_web_context(self):
        prompt = build_model_prompt(
            "RaiNz",
            "What is Softia?",
            [SearchResult("Softia docs", "https://example.com", "Discord bot docs")],
        )

        self.assertIn("Discord speaker: RaiNz", prompt)
        self.assertIn("What is Softia?", prompt)
        self.assertIn("Softia docs", prompt)
        self.assertIn("Discord bot docs", prompt)

    def test_build_model_prompt_handles_empty_web_context(self):
        prompt = build_model_prompt("RaiNz", "Hello", [])

        self.assertIn("no reliable results", prompt)

    def test_build_fallback_reply_uses_web_results(self):
        reply = build_fallback_reply(
            ChatError("API failed."),
            [SearchResult("Softia docs", "https://example.com", "Discord bot docs")],
        )

        self.assertIn("API failed.", reply)
        self.assertIn("https://example.com", reply)

    def test_response_needs_continuation_for_output_limit(self):
        response = SimpleNamespace(
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        )

        self.assertTrue(response_needs_continuation(response))

    def test_response_does_not_continue_other_incomplete_reasons(self):
        response = SimpleNamespace(
            status="incomplete",
            incomplete_details={"reason": "content_filter"},
        )

        self.assertFalse(response_needs_continuation(response))

    def test_response_does_not_continue_complete_response(self):
        response = SimpleNamespace(status="completed", incomplete_details=None)

        self.assertFalse(response_needs_continuation(response))


if __name__ == "__main__":
    unittest.main()
