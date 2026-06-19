import unittest

from bot.games import Card, finish_blackjack_round, hand_value, slot_multiplier


class GamesTest(unittest.TestCase):
    def test_hand_value_counts_aces_as_one_when_needed(self):
        cards = [Card("A", "♠"), Card("9", "♣"), Card("5", "♦")]

        self.assertEqual(hand_value(cards), 15)

    def test_finish_blackjack_round_player_wins_when_dealer_busts(self):
        session = _session(
            player=[Card("10", "♠"), Card("9", "♣")],
            dealer=[Card("10", "♦"), Card("6", "♣")],
            deck=[Card("10", "♥")],
            bet=20,
        )

        outcome, payout = finish_blackjack_round(session)

        self.assertIn("won", outcome)
        self.assertEqual(payout, 40)

    def test_slot_multiplier(self):
        self.assertEqual(slot_multiplier(["💎", "💎", "💎"]), 5)
        self.assertEqual(slot_multiplier(["🍒", "🍒", "🍒"]), 3)
        self.assertEqual(slot_multiplier(["🍒", "🍒", "⭐"]), 2)
        self.assertEqual(slot_multiplier(["🍒", "🔔", "⭐"]), 0)


def _session(player, dealer, deck, bet):
    from bot.games import BlackjackSession

    return BlackjackSession(guild_id=1, user_id=2, bet=bet, deck=deck, player=player, dealer=dealer)


if __name__ == "__main__":
    unittest.main()
