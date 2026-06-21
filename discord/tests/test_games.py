import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot.games import (
    BLACKJACK_CARD_BACK,
    CARD_SUITS,
    Card,
    blackjack_hand_line,
    dice_animation_frames,
    dice_face,
    finish_blackjack_round,
    game_info_embed,
    hand_value,
    slot_animation_frames,
    slot_multiplier,
    user_display_name,
)


class GamesTest(unittest.IsolatedAsyncioTestCase):
    def test_hand_value_counts_aces_as_one_when_needed(self):
        cards = [Card("A", "♠"), Card("9", "♣"), Card("5", "♦")]

        self.assertEqual(hand_value(cards), 15)

    def test_card_suits_keep_black_suits_readable(self):
        self.assertEqual(CARD_SUITS, ("\u2660\ufe0e", "\u2665\ufe0f", "\u2666\ufe0f", "\u2663\ufe0e"))

    def test_hidden_blackjack_hand_uses_card_back(self):
        cards = [Card("A", CARD_SUITS[0]), Card("K", CARD_SUITS[1])]

        line, value = blackjack_hand_line(cards, reveal=False)

        self.assertIn(BLACKJACK_CARD_BACK, line)
        self.assertEqual(value, "?")

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

    def test_game_info_embed_lists_animated_games(self):
        data = game_info_embed().to_dict()

        self.assertEqual(data["title"], "Game Hub")
        self.assertIn("animated reels", data["fields"][1]["value"])
        self.assertIn("animated dice", data["fields"][1]["value"])

    def test_dice_animation_finishes_on_final_roll(self):
        frames = dice_animation_frames(6)

        self.assertEqual(frames[-1], dice_face(6))

    def test_slot_animation_finishes_on_final_result(self):
        result = ["🍒", "🍋", "💎"]

        frames = slot_animation_frames(result)

        self.assertEqual(frames[-1], result)

    async def test_user_display_name_uses_cached_member(self):
        bot = SimpleNamespace(fetch_user=AsyncMock())
        guild = SimpleNamespace(get_member=Mock(return_value=SimpleNamespace(display_name="CachedName")))

        self.assertEqual(await user_display_name(bot, guild, 123), "CachedName")
        bot.fetch_user.assert_not_called()

    async def test_user_display_name_fetches_user_when_not_cached(self):
        bot = SimpleNamespace(fetch_user=AsyncMock(return_value=SimpleNamespace(display_name="FetchedName")))
        guild = SimpleNamespace(get_member=Mock(return_value=None))

        self.assertEqual(await user_display_name(bot, guild, 123), "FetchedName")
        bot.fetch_user.assert_awaited_once_with(123)


def _session(player, dealer, deck, bet):
    from bot.games import BlackjackSession

    return BlackjackSession(guild_id=1, user_id=2, bet=bet, deck=deck, player=player, dealer=dealer)


if __name__ == "__main__":
    unittest.main()
