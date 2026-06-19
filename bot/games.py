from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

import discord
from discord.ext import commands

from .game_store import (
    DAILY_REWARD,
    GameStore,
    GameStoreError,
    SHOP_ITEMS,
    format_coins,
    format_duration,
)
from .messages import GAME_INFO_MESSAGE


CARD_SUITS = ("♠", "♥", "♦", "♣")
CARD_RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SLOT_SYMBOLS = ("🍒", "🍋", "🔔", "⭐", "💎")


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def label(self) -> str:
        return f"{self.rank}{self.suit}"


@dataclass
class BlackjackSession:
    guild_id: int
    user_id: int
    bet: int
    deck: list[Card] = field(default_factory=list)
    player: list[Card] = field(default_factory=list)
    dealer: list[Card] = field(default_factory=list)
    finished: bool = False

    @classmethod
    def create(cls, guild_id: int, user_id: int, bet: int) -> "BlackjackSession":
        deck = build_deck()
        random.shuffle(deck)
        session = cls(guild_id=guild_id, user_id=user_id, bet=bet, deck=deck)
        session.player.extend([session.draw(), session.draw()])
        session.dealer.extend([session.draw(), session.draw()])
        return session

    def draw(self) -> Card:
        return self.deck.pop()


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = GameStore()
        self._blackjack_sessions: set[tuple[int, int]] = set()

    @commands.command(name="gameinfo")
    async def game_info(self, ctx: commands.Context) -> None:
        await ctx.send(GAME_INFO_MESSAGE)

    @commands.command(name="wallet", aliases=["bal", "balance"])
    @commands.guild_only()
    async def wallet(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        balance = self.store.balance(ctx.guild.id, target.id)
        await ctx.send(f"{target.display_name}'s wallet: {format_coins(balance)}")

    @commands.command(name="daily")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context) -> None:
        balance, remaining = self.store.claim_daily(ctx.guild.id, ctx.author.id)
        if remaining is not None:
            await ctx.send(f"Daily already claimed. Try again in `{format_duration(remaining)}`.")
            return

        await ctx.send(f"You claimed {format_coins(DAILY_REWARD)}. Balance: {format_coins(balance)}")

    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context) -> None:
        lines = ["Shop:"]
        for item in SHOP_ITEMS:
            lines.append(f"`{item.item_id}` - {item.name} - {format_coins(item.price)} - {item.description}")
        lines.append("Use `-buy <item_id> [quantity]`.")
        await ctx.send("\n".join(lines))

    @commands.command(name="buy")
    @commands.guild_only()
    async def buy(self, ctx: commands.Context, item_id: str, quantity: int = 1) -> None:
        try:
            item, balance = self.store.buy_item(ctx.guild.id, ctx.author.id, item_id, quantity)
        except GameStoreError as exc:
            await ctx.send(str(exc))
            return

        await ctx.send(f"Bought `{quantity}x {item.name}`. Balance: {format_coins(balance)}")

    @commands.command(name="inventory", aliases=["inv"])
    @commands.guild_only()
    async def inventory(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        inventory = self.store.inventory(ctx.guild.id, target.id)
        if not inventory:
            await ctx.send(f"{target.display_name}'s inventory is empty.")
            return

        item_names = {item.item_id: item.name for item in SHOP_ITEMS}
        lines = [f"{target.display_name}'s inventory:"]
        for item_id, quantity in sorted(inventory.items()):
            lines.append(f"- {item_names.get(item_id, item_id)} x{quantity}")
        await ctx.send("\n".join(lines))

    @commands.command(name="leaderboard", aliases=["topcoins"])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context) -> None:
        entries = self.store.leaderboard(ctx.guild.id, 10)
        if not entries:
            await ctx.send("No wallets yet.")
            return

        lines = ["Coin leaderboard:"]
        for index, (user_id, balance) in enumerate(entries, start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            lines.append(f"{index}. {name} - {format_coins(balance)}")
        await ctx.send("\n".join(lines))

    @commands.command(name="coinflip", aliases=["cf"])
    @commands.guild_only()
    async def coinflip(self, ctx: commands.Context, choice: str, bet: int) -> None:
        normalized = choice.lower()
        if normalized not in {"heads", "tails", "cara", "coroa"}:
            await ctx.send("Usage: `-coinflip <heads/tails> <bet>`")
            return

        picked_heads = normalized in {"heads", "cara"}
        result_heads = random.choice([True, False])
        result_label = "heads" if result_heads else "tails"

        if not await self._take_bet(ctx, bet):
            return

        if picked_heads == result_heads:
            balance = self.store.add_coins(ctx.guild.id, ctx.author.id, bet * 2)
            await ctx.send(f"Coin landed on `{result_label}`. You won {format_coins(bet)}. Balance: {format_coins(balance)}")
            return

        balance = self.store.balance(ctx.guild.id, ctx.author.id)
        await ctx.send(f"Coin landed on `{result_label}`. You lost {format_coins(bet)}. Balance: {format_coins(balance)}")

    @commands.command(name="dice")
    @commands.guild_only()
    async def dice(self, ctx: commands.Context, guess: int, bet: int) -> None:
        if guess < 1 or guess > 6:
            await ctx.send("Usage: `-dice <1-6> <bet>`")
            return

        if not await self._take_bet(ctx, bet):
            return

        roll = random.randint(1, 6)
        if roll == guess:
            winnings = bet * 6
            balance = self.store.add_coins(ctx.guild.id, ctx.author.id, winnings)
            await ctx.send(f"Rolled `{roll}`. Exact hit. You won {format_coins(winnings - bet)}. Balance: {format_coins(balance)}")
            return

        balance = self.store.balance(ctx.guild.id, ctx.author.id)
        await ctx.send(f"Rolled `{roll}`. You lost {format_coins(bet)}. Balance: {format_coins(balance)}")

    @commands.command(name="slots", aliases=["slot"])
    @commands.guild_only()
    async def slots(self, ctx: commands.Context, bet: int) -> None:
        if not await self._take_bet(ctx, bet):
            return

        result = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        multiplier = slot_multiplier(result)
        if multiplier:
            payout = bet * multiplier
            balance = self.store.add_coins(ctx.guild.id, ctx.author.id, payout)
            await ctx.send(f"{' '.join(result)}\nYou won {format_coins(payout - bet)}. Balance: {format_coins(balance)}")
            return

        balance = self.store.balance(ctx.guild.id, ctx.author.id)
        await ctx.send(f"{' '.join(result)}\nYou lost {format_coins(bet)}. Balance: {format_coins(balance)}")

    @commands.command(name="blackjack", aliases=["bj"])
    @commands.guild_only()
    async def blackjack(self, ctx: commands.Context, bet: int) -> None:
        key = (ctx.guild.id, ctx.author.id)
        if key in self._blackjack_sessions:
            await ctx.send("You already have an active blackjack game.")
            return

        if not await self._take_bet(ctx, bet):
            return

        session = BlackjackSession.create(ctx.guild.id, ctx.author.id, bet)
        self._blackjack_sessions.add(key)
        view = BlackjackView(self, session, ctx.author.id)

        if hand_value(session.player) == 21:
            await view.finish(ctx, "Blackjack!", blackjack=True)
            return

        await ctx.send(render_blackjack(session), view=view)

    async def _take_bet(self, ctx: commands.Context, bet: int) -> bool:
        if ctx.guild is None:
            return False

        try:
            self.store.spend_coins(ctx.guild.id, ctx.author.id, bet)
        except GameStoreError as exc:
            await ctx.send(str(exc))
            return False

        return True

    def finish_blackjack(self, session: BlackjackSession, payout: int) -> int:
        session.finished = True
        self._blackjack_sessions.discard((session.guild_id, session.user_id))
        if payout > 0:
            return self.store.add_coins(session.guild_id, session.user_id, payout)
        return self.store.balance(session.guild_id, session.user_id)


class BlackjackView(discord.ui.View):
    def __init__(self, cog: GamesCog, session: BlackjackSession, owner_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.session = session
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message("This is not your blackjack game.", ephemeral=True)
        return False

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.session.player.append(self.session.draw())
        if hand_value(self.session.player) > 21:
            balance = self.cog.finish_blackjack(self.session, 0)
            self._disable()
            await interaction.response.edit_message(
                content=f"{render_blackjack(self.session, reveal_dealer=True)}\nBust. You lost {format_coins(self.session.bet)}. Balance: {format_coins(balance)}",
                view=self,
            )
            return

        await interaction.response.edit_message(content=render_blackjack(self.session), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        outcome, payout = finish_blackjack_round(self.session)
        balance = self.cog.finish_blackjack(self.session, payout)
        self._disable()
        await interaction.response.edit_message(
            content=f"{render_blackjack(self.session, reveal_dealer=True)}\n{outcome} Balance: {format_coins(balance)}",
            view=self,
        )

    async def on_timeout(self) -> None:
        if self.session.finished:
            return
        self.cog.finish_blackjack(self.session, 0)

    async def finish(self, ctx: commands.Context, outcome: str, blackjack: bool = False) -> None:
        payout = int(self.session.bet * 2.5) if blackjack else self.session.bet * 2
        balance = self.cog.finish_blackjack(self.session, payout)
        self._disable()
        await ctx.send(
            f"{render_blackjack(self.session, reveal_dealer=True)}\n{outcome} Balance: {format_coins(balance)}",
            view=self,
        )

    def _disable(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


def build_deck() -> list[Card]:
    return [Card(rank, suit) for suit in CARD_SUITS for rank in CARD_RANKS]


def hand_value(cards: list[Card]) -> int:
    total = 0
    aces = 0
    for card in cards:
        if card.rank == "A":
            aces += 1
            total += 11
        elif card.rank in {"J", "Q", "K"}:
            total += 10
        else:
            total += int(card.rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total


def render_blackjack(session: BlackjackSession, reveal_dealer: bool = False) -> str:
    player_cards = " ".join(card.label() for card in session.player)
    player_value = hand_value(session.player)

    if reveal_dealer:
        dealer_cards = " ".join(card.label() for card in session.dealer)
        dealer_value = hand_value(session.dealer)
    else:
        dealer_cards = f"{session.dealer[0].label()} ??"
        dealer_value = "?"

    return (
        f"Blackjack bet: {format_coins(session.bet)}\n"
        f"Dealer: {dealer_cards} ({dealer_value})\n"
        f"Player: {player_cards} ({player_value})"
    )


def finish_blackjack_round(session: BlackjackSession) -> tuple[str, int]:
    while hand_value(session.dealer) < 17:
        session.dealer.append(session.draw())

    player_value = hand_value(session.player)
    dealer_value = hand_value(session.dealer)

    if dealer_value > 21 or player_value > dealer_value:
        return f"You won {format_coins(session.bet)}.", session.bet * 2
    if player_value == dealer_value:
        return "Push. Bet returned.", session.bet
    return f"You lost {format_coins(session.bet)}.", 0


def slot_multiplier(result: list[str]) -> int:
    if len(set(result)) == 1:
        return 5 if result[0] == "💎" else 3

    if len(set(result)) == 2:
        return 2

    return 0
