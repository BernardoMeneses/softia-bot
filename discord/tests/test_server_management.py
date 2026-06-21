import unittest

from bot.server_management import EventSpec, RANDOM_EVENTS, ServerManagementCog, _render_event


class ServerManagementTest(unittest.TestCase):
    def test_render_poll_event_counts_votes(self):
        event = EventSpec("Poll", "Pick one.", ("A", "B"))

        rendered = _render_event(event, [2, 1])

        self.assertIn("A: 2 vote(s)", rendered)
        self.assertIn("B: 1 vote(s)", rendered)

    def test_render_quiz_event_winner(self):
        event = EventSpec("Quiz", "Question?", ("Wrong", "Right"), correct_index=1, reward=25)

        rendered = _render_event(event, winner="@user", reward_line="Reward: coin")

        self.assertIn("@user got it right", rendered)
        self.assertIn("Answer: Right", rendered)
        self.assertIn("Reward: coin", rendered)

    def test_render_race_event(self):
        event = EventSpec("Race", "Click fast.", ("Claim",), event_type="race", reward=20)

        rendered = _render_event(event, winner="@user", reward_line="Reward: coin")

        self.assertIn("First valid click wins", rendered)
        self.assertIn("@user won the race", rendered)
        self.assertIn("Reward: coin", rendered)

    def test_render_challenge_event_shows_participants(self):
        event = EventSpec("Challenge", "Pick a lane.", ("Build", "Test"), event_type="challenge")

        rendered = _render_event(
            event,
            [1, 0],
            participants={0: {10}, 1: set()},
            user_labels={10: "RaiNz"},
        )

        self.assertIn("Build: 1 participant(s) - RaiNz", rendered)
        self.assertIn("Join a lane", rendered)

    def test_render_mystery_event_tracks_attempts(self):
        event = EventSpec(
            "Mystery",
            "Pick one.",
            ("Door A", "Door B"),
            correct_index=1,
            event_type="mystery",
            reward=30,
        )

        rendered = _render_event(event, [2, 1], winner="@user", reward_line="Reward: coin")

        self.assertIn("Door A: 2 attempt(s)", rendered)
        self.assertIn("@user opened the right choice: Door B", rendered)
        self.assertIn("Reward: coin", rendered)

    def test_render_closed_event_marks_status(self):
        event = EventSpec("Poll", "Pick one.", ("A", "B"))

        rendered = _render_event(event, [0, 0], closed=True)

        self.assertIn("Status: closed.", rendered)

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
