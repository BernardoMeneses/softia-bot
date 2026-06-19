import unittest

from bot.server_management import EventSpec, RANDOM_EVENTS, ServerManagementCog, _render_event


class ServerManagementTest(unittest.TestCase):
    def test_render_poll_event_counts_votes(self):
        event = EventSpec("Poll", "Pick one.", ("A", "B"))

        rendered = _render_event(event, [2, 1])

        self.assertIn("A: 2 vote(s)", rendered)
        self.assertIn("B: 1 vote(s)", rendered)

    def test_render_quiz_event_winner(self):
        event = EventSpec("Quiz", "Question?", ("Wrong", "Right"), correct_index=1)

        rendered = _render_event(event, winner="@user")

        self.assertIn("@user got it right", rendered)
        self.assertIn("Answer: Right", rendered)

    def test_next_event_rotates_without_repeats_until_bag_is_empty(self):
        cog = ServerManagementCog.__new__(ServerManagementCog)
        cog._event_bags = {}

        seen = [cog._next_event(123) for _ in range(len(RANDOM_EVENTS))]

        self.assertEqual(len(set(seen)), len(RANDOM_EVENTS))

    def test_next_event_refills_after_full_rotation(self):
        cog = ServerManagementCog.__new__(ServerManagementCog)
        cog._event_bags = {}

        for _ in range(len(RANDOM_EVENTS)):
            cog._next_event(123)

        self.assertIn(cog._next_event(123), RANDOM_EVENTS)


if __name__ == "__main__":
    unittest.main()
