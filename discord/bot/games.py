from __future__ import annotations

import asyncio
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


CARD_SUITS = ("\u2660\ufe0e", "\u2665\ufe0f", "\u2666\ufe0f", "\u2663\ufe0e")
CARD_RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SLOT_SYMBOLS = ("\U0001f352", "\U0001f34b", "\U0001f514", "\u2b50", "\U0001f48e")
BLACKJACK_CARD_BACK = "\U0001f0a0"
DICE_FACES = ("\u2680", "\u2681", "\u2682", "\u2683", "\u2684", "\u2685")
SPINNING_SLOT = "\u2754"
DICE_SHAKE = "\U0001f3b2"


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
        await _send_game_card(ctx, game_info_embed(), GAME_INFO_MESSAGE)

    @commands.command(name="wallet", aliases=["bal", "balance"])
    @commands.guild_only()
    async def wallet(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        balance = self.store.balance(ctx.guild.id, target.id)
        await _send_game_card(
            ctx,
            game_embed(
                "Coin Wallet",
                f"{target.display_name}'s coin balance.",
                fields=(("Balance", format_coins(balance), False),),
                color=discord.Color.gold(),
                footer="Use -daily to claim coins and -shop to spend them.",
            ),
            f"{target.display_name}'s wallet: {format_coins(balance)}",
        )

    @commands.command(name="daily")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context) -> None:
        balance, remaining = self.store.claim_daily(ctx.guild.id, ctx.author.id)
        if remaining is not None:
            await _send_game_card(
                ctx,
                game_embed(
                    "Daily Reward",
                    "You already claimed today's reward.",
                    fields=(("Try again in", format_duration(remaining), False),),
                    color=discord.Color.orange(),
                ),
                f"Daily already claimed. Try again in `{format_duration(remaining)}`.",
            )
            return

        await _send_game_card(
            ctx,
            game_embed(
                "Daily Reward",
                "Daily coins claimed.",
                fields=(
                    ("Reward", format_coins(DAILY_REWARD), True),
                    ("Balance", format_coins(balance), True),
                ),
                color=discord.Color.green(),
            ),
            f"You claimed {format_coins(DAILY_REWARD)}. Balance: {format_coins(balance)}",
        )

    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context) -> None:
        lines = ["Shop:"]
        fields = []
        for item in SHOP_ITEMS:
            lines.append(f"`{item.item_id}` - {item.name} - {format_coins(item.price)} - {item.description}")
            fields.append((f"{item.name} (`{item.item_id}`)", f"{format_coins(item.price)}\n{item.description}", False))
        lines.append("Use `-buy <item_id> [quantity]`.")
        await _send_game_card(
            ctx,
            game_embed(
                "Shop",
                "Buy cosmetic items with your coins.",
                fields=tuple(fields),
                color=discord.Color.blurple(),
                footer="Use -buy <item_id> [quantity].",
            ),
            "\n".join(lines),
        )

    @commands.command(name="buy")
    @commands.guild_only()
    async def buy(self, ctx: commands.Context, item_id: str, quantity: int = 1) -> None:
        try:
            item, balance = self.store.buy_item(ctx.guild.id, ctx.author.id, item_id, quantity)
        except GameStoreError as exc:
            await ctx.send(str(exc))
            return

        await _send_game_card(
            ctx,
            game_embed(
                "Purchase Complete",
                f"Bought `{quantity}x {item.name}`.",
                fields=(("Balance", format_coins(balance), False),),
                color=discord.Color.green(),
            ),
            f"Bought `{quantity}x {item.name}`. Balance: {format_coins(balance)}",
        )

    @commands.command(name="inventory", aliases=["inv"])
    @commands.guild_only()
    async def inventory(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        inventory = self.store.inventory(ctx.guild.id, target.id)
        if not inventory:
            await _send_game_card(
                ctx,
                game_embed(
                    "Inventory",
                    f"{target.display_name}'s inventory is empty.",
                    color=discord.Color.dark_grey(),
                ),
                f"{target.display_name}'s inventory is empty.",
            )
            return

        item_names = {item.item_id: item.name for item in SHOP_ITEMS}
        lines = [f"{target.display_name}'s inventory:"]
        fields = []
        for item_id, quantity in sorted(inventory.items()):
            lines.append(f"- {item_names.get(item_id, item_id)} x{quantity}")
            fields.append((item_names.get(item_id, item_id), f"x{quantity}", True))
        await _send_game_card(
            ctx,
            game_embed(
                "Inventory",
                f"{target.display_name}'s items.",
                fields=tuple(fields),
                color=discord.Color.blurple(),
            ),
            "\n".join(lines),
        )

    @commands.command(name="leaderboard", aliases=["topcoins"])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context) -> None:
        entries = self.store.leaderboard(ctx.guild.id, 10)
        if not entries:
            await _send_game_card(
                ctx,
                game_embed("Coin Leaderboard", "No wallets yet.", color=discord.Color.dark_grey()),
                "No wallets yet.",
            )
            return

        lines = ["Coin leaderboard:"]
        for index, (user_id, balance) in enumerate(entries, start=1):
            name = await user_display_name(self.bot, ctx.guild, user_id)
            lines.append(f"{index}. {name} - {format_coins(balance)}")
        await _send_game_card(
            ctx,
            game_embed(
                "Coin Leaderboard",
                "\n".join(lines[1:]),
                color=discord.Color.gold(),
            ),
            "\n".join(lines),
        )

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
            await _send_game_card(
                ctx,
            game_embed(
                "Coin Flip",
                coinflip_description(result_label, won=True),
                fields=(
                    ("Result", f"You won {format_coins(bet)}", True),
                    ("Balance", format_coins(balance), True),
                ),
                color=discord.Color.green(),
                ),
                f"Coin landed on `{result_label}`. You won {format_coins(bet)}. Balance: {format_coins(balance)}",
            )
            return

        balance = self.store.balance(ctx.guild.id, ctx.author.id)
        await _send_game_card(
            ctx,
            game_embed(
                "Coin Flip",
                coinflip_description(result_label, won=False),
                fields=(
                    ("Result", f"You lost {format_coins(bet)}", True),
                    ("Balance", format_coins(balance), True),
                ),
                color=discord.Color.red(),
            ),
            f"Coin landed on `{result_label}`. You lost {format_coins(bet)}. Balance: {format_coins(balance)}",
        )

    @commands.command(name="dice")
    @commands.guild_only()
    async def dice(self, ctx: commands.Context, guess: int, bet: int) -> None:
        if guess < 1 or guess > 6:
            await ctx.send("Usage: `-dice <1-6> <bet>`")
            return

        if not await self._take_bet(ctx, bet):
            return

        roll = random.randint(1, 6)
        message, use_embeds = await _send_game_card(
            ctx,
            dice_embed(ctx.author.display_name, guess, bet, DICE_SHAKE, "Rolling..."),
            dice_text(ctx.author.display_name, guess, bet, DICE_SHAKE, "Rolling..."),
        )
        for face in dice_animation_frames(roll):
            await asyncio.sleep(0.35)
            await _edit_game_card(
                message,
                use_embeds,
                dice_embed(ctx.author.display_name, guess, bet, face, "Rolling..."),
                dice_text(ctx.author.display_name, guess, bet, face, "Rolling..."),
            )

        if roll == guess:
            winnings = bet * 6
            balance = self.store.add_coins(ctx.guild.id, ctx.author.id, winnings)
            result = f"Exact hit. You won {format_coins(winnings - bet)}."
            await _edit_game_card(
                message,
                use_embeds,
                dice_embed(
                    ctx.author.display_name,
                    guess,
                    bet,
                    dice_face(roll),
                    result,
                    balance=balance,
                    color=discord.Color.green(),
                ),
                dice_text(ctx.author.display_name, guess, bet, dice_face(roll), f"{result} Balance: {format_coins(balance)}"),
            )
            return

        balance = self.store.balance(ctx.guild.id, ctx.author.id)
        result = f"You lost {format_coins(bet)}."
        await _edit_game_card(
            message,
            use_embeds,
            dice_embed(
                ctx.author.display_name,
                guess,
                bet,
                dice_face(roll),
                result,
                balance=balance,
                color=discord.Color.red(),
            ),
            dice_text(ctx.author.display_name, guess, bet, dice_face(roll), f"{result} Balance: {format_coins(balance)}"),
        )

    @commands.command(name="slots", aliases=["slot"])
    @commands.guild_only()
    async def slots(self, ctx: commands.Context, bet: int) -> None:
        if not await self._take_bet(ctx, bet):
            return

        result = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        message, use_embeds = await _send_game_card(
            ctx,
            slots_embed(ctx.author.display_name, bet, [SPINNING_SLOT, SPINNING_SLOT, SPINNING_SLOT], "Spinning..."),
            slots_text(ctx.author.display_name, bet, [SPINNING_SLOT, SPINNING_SLOT, SPINNING_SLOT], "Spinning..."),
        )
        for frame in slot_animation_frames(result):
            await asyncio.sleep(0.45)
            await _edit_game_card(
                message,
                use_embeds,
                slots_embed(ctx.author.display_name, bet, frame, "Spinning..."),
                slots_text(ctx.author.display_name, bet, frame, "Spinning..."),
            )

        multiplier = slot_multiplier(result)
        if multiplier:
            payout = bet * multiplier
            balance = self.store.add_coins(ctx.guild.id, ctx.author.id, payout)
            outcome = f"x{multiplier}. You won {format_coins(payout - bet)}."
            await _edit_game_card(
                message,
                use_embeds,
                slots_embed(ctx.author.display_name, bet, result, outcome, balance=balance, color=discord.Color.green()),
                slots_text(ctx.author.display_name, bet, result, f"{outcome} Balance: {format_coins(balance)}"),
            )
            return

        balance = self.store.balance(ctx.guild.id, ctx.author.id)
        outcome = f"You lost {format_coins(bet)}."
        await _edit_game_card(
            message,
            use_embeds,
            slots_embed(ctx.author.display_name, bet, result, outcome, balance=balance, color=discord.Color.red()),
            slots_text(ctx.author.display_name, bet, result, f"{outcome} Balance: {format_coins(balance)}"),
        )

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
        use_embeds = _channel_can_embed(ctx.channel)
        view = BlackjackView(self, session, ctx.author.id, use_embeds=use_embeds)

        if hand_value(session.player) == 21:
            await view.finish(ctx, "Blackjack!", blackjack=True)
            return

        message = await ctx.send(**blackjack_payload(session, view, use_embeds=use_embeds))
        view.message = message

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
    def __init__(self, cog: GamesCog, session: BlackjackSession, owner_id: int, *, use_embeds: bool):
        super().__init__(timeout=120)
        self.cog = cog
        self.session = session
        self.owner_id = owner_id
        self.use_embeds = use_embeds
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message("This is not your blackjack game.", ephemeral=True)
        return False

    @discord.ui.button(label="Hit", emoji="\U0001f0cf", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.session.player.append(self.session.draw())
        if hand_value(self.session.player) > 21:
            balance = self.cog.finish_blackjack(self.session, 0)
            self._disable()
            await interaction.response.edit_message(
                **blackjack_payload(
                    self.session,
                    self,
                    use_embeds=self.use_embeds,
                    reveal_dealer=True,
                    outcome=f"Bust. You lost {format_coins(self.session.bet)}.",
                    balance=balance,
                    color=discord.Color.red(),
                )
            )
            return

        await interaction.response.edit_message(**blackjack_payload(self.session, self, use_embeds=self.use_embeds))

    @discord.ui.button(label="Stand", emoji="\u270b", style=discord.ButtonStyle.success)
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        outcome, payout = finish_blackjack_round(self.session)
        balance = self.cog.finish_blackjack(self.session, payout)
        self._disable()
        await interaction.response.edit_message(
            **blackjack_payload(
                self.session,
                self,
                use_embeds=self.use_embeds,
                reveal_dealer=True,
                outcome=outcome,
                balance=balance,
                color=blackjack_result_color(payout, self.session.bet),
            )
        )

    async def on_timeout(self) -> None:
        if self.session.finished:
            return
        balance = self.cog.finish_blackjack(self.session, 0)
        self._disable()

        if self.message is None:
            return

        try:
            await self.message.edit(
                **blackjack_payload(
                    self.session,
                    self,
                    use_embeds=self.use_embeds,
                    reveal_dealer=True,
                    outcome=f"Timed out. You lost {format_coins(self.session.bet)}.",
                    balance=balance,
                    color=discord.Color.red(),
                )
            )
        except discord.HTTPException:
            return

    async def finish(self, ctx: commands.Context, outcome: str, blackjack: bool = False) -> None:
        payout = int(self.session.bet * 2.5) if blackjack else self.session.bet * 2
        balance = self.cog.finish_blackjack(self.session, payout)
        self._disable()
        self.message = await ctx.send(
            **blackjack_payload(
                self.session,
                self,
                use_embeds=self.use_embeds,
                reveal_dealer=True,
                outcome=outcome,
                balance=balance,
                color=discord.Color.green(),
            )
        )

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        message = "A interacao do blackjack falhou. Tenta novamente."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    def _disable(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


def game_embed(
    title: str,
    description: str = "",
    *,
    fields: tuple[tuple[str, str, bool], ...] = (),
    color: discord.Color | None = None,
    footer: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or discord.Color.blurple(),
    )
    for name, value, inline in fields:
        embed.add_field(name=name, value=value or "-", inline=inline)
    if footer:
        embed.set_footer(text=footer)
    return embed


def game_info_embed() -> discord.Embed:
    return game_embed(
        "Game Hub",
        "Economy, casino games and coin rewards.",
        fields=(
            (
                "Economy",
                "`-wallet [@member]`\n`-daily`\n`-shop`\n`-buy <item_id> [quantity]`\n`-inventory [@member]`\n`-leaderboard`",
                False,
            ),
            (
                "Games",
                "`-blackjack <bet>` interactive table\n`-coinflip <heads/tails> <bet>` coin card\n`-slots <bet>` animated reels\n`-dice <1-6> <bet>` animated dice",
                False,
            ),
            ("Payouts", "Dice exact hit pays x6. Slots pay x2/x3/x5 depending on symbols.", False),
        ),
        color=discord.Color.gold(),
        footer="All games use the same wallet balance.",
    )


async def _send_game_card(
    ctx: commands.Context,
    embed: discord.Embed,
    fallback: str,
    *,
    view: discord.ui.View | None = None,
) -> tuple[discord.Message, bool]:
    use_embeds = _channel_can_embed(ctx.channel)
    if use_embeds:
        return await ctx.send(embed=embed, view=view), True

    return await ctx.send(fallback, view=view), False


async def _edit_game_card(
    message: discord.Message,
    use_embeds: bool,
    embed: discord.Embed,
    fallback: str,
    *,
    view: discord.ui.View | None = None,
) -> None:
    if use_embeds:
        await message.edit(embed=embed, view=view)
        return

    await message.edit(content=fallback, view=view)


def _channel_can_embed(channel: object) -> bool:
    guild = getattr(channel, "guild", None)
    if guild is None:
        return True

    bot_member = getattr(guild, "me", None)
    if bot_member is None or not hasattr(channel, "permissions_for"):
        return False

    return bool(channel.permissions_for(bot_member).embed_links)


def blackjack_payload(
    session: BlackjackSession,
    view: discord.ui.View,
    *,
    use_embeds: bool,
    reveal_dealer: bool = False,
    outcome: str | None = None,
    balance: int | None = None,
    color: discord.Color | None = None,
) -> dict[str, object]:
    if use_embeds:
        return {
            "embed": blackjack_embed(
                session,
                reveal_dealer=reveal_dealer,
                outcome=outcome,
                balance=balance,
                color=color,
            ),
            "view": view,
        }

    content = render_blackjack(session, reveal_dealer=reveal_dealer)
    if outcome:
        content = f"{content}\n{outcome}"
    if balance is not None:
        content = f"{content} Balance: {format_coins(balance)}"
    return {"content": content, "view": view}


def blackjack_embed(
    session: BlackjackSession,
    *,
    reveal_dealer: bool = False,
    outcome: str | None = None,
    balance: int | None = None,
    color: discord.Color | None = None,
) -> discord.Embed:
    dealer_cards, dealer_value = blackjack_hand_line(session.dealer, reveal_dealer)
    player_cards, player_value = blackjack_hand_line(session.player, True)
    fields = [
        ("Dealer Hand", f"{dealer_cards}\nValue: `{dealer_value}`", False),
        ("Your Hand", f"{player_cards}\nValue: `{player_value}`", False),
        ("Table", f"Bet: {format_coins(session.bet)}\nDeck: `{len(session.deck)}` cards left", True),
    ]
    if balance is not None:
        fields.append(("Balance", format_coins(balance), True))
    if outcome:
        fields.append(("Result", outcome, False))

    return game_embed(
        "Blackjack Table",
        blackjack_status_text(session, reveal_dealer=reveal_dealer),
        fields=tuple(fields),
        color=color or discord.Color.dark_teal(),
        footer="Hit draws one card. Stand reveals the dealer. Timeout loses the bet.",
    )


def blackjack_hand_line(cards: list[Card], reveal: bool) -> tuple[str, str]:
    if reveal:
        return " ".join(card.label() for card in cards), str(hand_value(cards))

    return f"{cards[0].label()} {BLACKJACK_CARD_BACK}", "?"


def blackjack_status_text(session: BlackjackSession, *, reveal_dealer: bool) -> str:
    player_value = hand_value(session.player)
    if reveal_dealer:
        dealer_value = hand_value(session.dealer)
        return f"Round closed. Dealer `{dealer_value}` vs player `{player_value}`."

    if player_value == 21:
        return "Blackjack pressure. Stand to reveal or enjoy the natural win."
    if player_value >= 18:
        return f"Strong hand at `{player_value}`. Stand is safe, hit is spicy."
    if player_value <= 11:
        return f"Safe hit zone at `{player_value}`."
    return f"Player value `{player_value}`. Choose Hit or Stand."


def blackjack_result_color(payout: int, bet: int) -> discord.Color:
    if payout > bet:
        return discord.Color.green()
    if payout == bet:
        return discord.Color.gold()
    return discord.Color.red()


def dice_embed(
    player_name: str,
    guess: int,
    bet: int,
    face: str,
    status: str,
    *,
    balance: int | None = None,
    color: discord.Color | None = None,
) -> discord.Embed:
    fields = [
        ("Player", player_name, True),
        ("Guess", str(guess), True),
        ("Bet", format_coins(bet), True),
        ("Dice", f"## {face}", False),
        ("Status", status, False),
    ]
    if balance is not None:
        fields.append(("Balance", format_coins(balance), True))

    return game_embed(
        "Dice Roll",
        "Exact hit pays x6. The roll updates live before locking the result.",
        fields=tuple(fields),
        color=color or discord.Color.blurple(),
    )


def dice_text(player_name: str, guess: int, bet: int, face: str, status: str) -> str:
    return f"Dice Roll\nPlayer: {player_name}\nGuess: {guess}\nBet: {format_coins(bet)}\nDice: {face}\n{status}"


def dice_face(roll: int) -> str:
    return DICE_FACES[roll - 1]


def dice_animation_frames(final_roll: int) -> list[str]:
    frames = [dice_face(random.randint(1, 6)) for _ in range(4)]
    frames.append(dice_face(final_roll))
    return frames


def slots_embed(
    player_name: str,
    bet: int,
    symbols: list[str],
    status: str,
    *,
    balance: int | None = None,
    color: discord.Color | None = None,
) -> discord.Embed:
    fields = [
        ("Player", player_name, True),
        ("Bet", format_coins(bet), True),
        ("Machine", slot_machine_line(symbols), False),
        ("Status", status, False),
    ]
    if balance is not None:
        fields.append(("Balance", format_coins(balance), True))

    return game_embed(
        "Slot Machine",
        "Three equal symbols pay high. Two equal symbols still pay. The reels stop one by one.",
        fields=tuple(fields),
        color=color or discord.Color.gold(),
    )


def slots_text(player_name: str, bet: int, symbols: list[str], status: str) -> str:
    return f"Slot Machine\nPlayer: {player_name}\nBet: {format_coins(bet)}\n{slot_machine_line(symbols)}\n{status}"


def slot_machine_line(symbols: list[str]) -> str:
    return f"| {' | '.join(symbols)} |"


def coinflip_description(result_label: str, *, won: bool) -> str:
    face = "\U0001fa99"
    verdict = "You called it." if won else "Wrong side."
    return f"{face} The coin landed on `{result_label}`. {verdict}"


def slot_animation_frames(final_result: list[str]) -> list[list[str]]:
    return [
        [random.choice(SLOT_SYMBOLS) for _ in range(3)],
        [final_result[0], random.choice(SLOT_SYMBOLS), random.choice(SLOT_SYMBOLS)],
        [final_result[0], final_result[1], random.choice(SLOT_SYMBOLS)],
        final_result,
    ]


def build_deck() -> list[Card]:
    return [Card(rank, suit) for suit in CARD_SUITS for rank in CARD_RANKS]


async def user_display_name(bot: commands.Bot, guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    if member is not None:
        return member.display_name

    try:
        user = await bot.fetch_user(user_id)
    except discord.HTTPException:
        return f"User {user_id}"

    display_name = getattr(user, "display_name", None) or getattr(user, "global_name", None) or user.name
    return str(display_name)


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
        return 5 if result[0] == "\U0001f48e" else 3

    if len(set(result)) == 2:
        return 2

    return 0
