from __future__ import annotations

import os
import random
import logging
from dataclasses import dataclass
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Deque

import discord
from discord.ext import commands, tasks

from .game_store import GameStore, format_coins
from .games import GamesCog
from .messages import EVENTS_INFO_MESSAGE, SERVER_INFO_MESSAGE
from .server_settings import ServerSettings


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventSpec:
    title: str
    prompt: str
    options: tuple[str, ...]
    correct_index: int | None = None
    event_type: str = "poll"
    reward: int = 0
    stakes: str = ""
    success_text: str = ""
    failure_text: str = ""


RANDOM_EVENTS = (
    EventSpec(
        "Council Vote",
        "The server council needs a direction for the next hour. Pick the vibe.",
        ("Focus mode", "Chaos mode", "Music lounge", "Meme court"),
        stakes="Live vote. You can change your vote while the event is open.",
    ),
    EventSpec(
        "Late Night Protocol",
        "The server has entered night mode. Which protocol should activate?",
        ("Dark mode", "Low-fi music", "Silent grind", "Wrong answers"),
        stakes="Votes update the board instantly.",
    ),
    EventSpec(
        "Riddle Gate",
        "A locked channel door asks: what has keys but no locks?",
        ("Piano", "Map", "Clock", "Keyboard"),
        correct_index=0,
        event_type="quiz",
        reward=25,
        success_text="The gate opens.",
        failure_text="The lock buzzes. That answer is wrong.",
    ),
    EventSpec(
        "Creative Sprint",
        "Pick a prompt, then drop your answer in chat. The winning team gets bragging rights.",
        ("5-word story", "Project pitch", "Best shortcut", "One-line roast"),
        event_type="challenge",
        reward=8,
        stakes="Joining pays a small coin bonus once per user.",
    ),
    EventSpec(
        "Debate Drop",
        "A debate starts in the middle of the chat: working with music is...",
        ("Overrated", "Underrated", "Depends", "Only with headphones"),
        stakes="Pick a side. Switching sides is allowed.",
    ),
    EventSpec(
        "Server Quest Board",
        "Choose a quest and complete it in chat.",
        ("Share a useful tip", "Tag someone helpful", "Pitch a feature", "Post a tiny win"),
        event_type="challenge",
        reward=10,
        stakes="Each player can join one quest at a time.",
    ),
    EventSpec(
        "Rule Roulette",
        "Pick the temporary rule for this event thread.",
        ("No context memes", "Serious answers only", "Wrong answers only", "One-word replies"),
        stakes="The winning rule is the one with the most votes.",
    ),
    EventSpec(
        "Trivia Drop",
        "Which planet is known as the Red Planet?",
        ("Mars", "Venus", "Jupiter", "Mercury"),
        correct_index=0,
        event_type="quiz",
        reward=25,
        success_text="Correct. The astronomy badge is yours.",
        failure_text="Not this planet. Try again.",
    ),
    EventSpec(
        "Speed Vote",
        "The activity planner has three minutes of confidence. What should happen next?",
        ("Game night", "Code sprint", "Movie watch", "Music queue"),
        stakes="Fastest consensus wins the vibe.",
    ),
    EventSpec(
        "Emoji Trial",
        "Which reaction should represent 'approved' today?",
        ("Green check", "Fire", "Crown", "Skull"),
        stakes="The server chooses its temporary approval stamp.",
    ),
    EventSpec(
        "Logic Relay",
        "What comes next: 2, 4, 8, 16, ?",
        ("24", "32", "64", "128"),
        correct_index=1,
        event_type="quiz",
        reward=25,
        success_text="Sequence cracked.",
        failure_text="The pattern rejects that number.",
    ),
    EventSpec(
        "Roleplay Chain",
        "Choose the scenario for a 3-message improv chain.",
        ("Space station", "Secret agency", "Startup pitch", "Haunted office"),
        event_type="challenge",
        reward=8,
        stakes="Join a scenario, then continue the chain in chat.",
    ),
    EventSpec(
        "Click Race",
        "The signal dropped. First valid click claims the prize.",
        ("Sprint",),
        event_type="race",
        reward=20,
        success_text="Fastest hand in the server.",
    ),
    EventSpec(
        "Mystery Vault",
        "Three doors. One payout. Pick carefully; each user gets one attempt.",
        ("Door A", "Door B", "Door C"),
        correct_index=2,
        event_type="mystery",
        reward=30,
        success_text="The vault opens.",
        failure_text="That door was empty. You hear gears turning behind the wall.",
    ),
    EventSpec(
        "Server Bet",
        "What will happen first today?",
        ("Someone joins VC", "A meme appears", "A bug gets fixed", "A song is queued"),
        stakes="Prediction market, zero financial advice.",
    ),
    EventSpec(
        "Knowledge Check",
        "Which protocol powers most websites?",
        ("HTTP", "SMTP", "FTP", "SSH"),
        correct_index=0,
        event_type="quiz",
        reward=25,
        success_text="Correct. Web brain activated.",
        failure_text="Close, but not the web one.",
    ),
    EventSpec(
        "Squad Builder",
        "Choose your team for the next mini activity.",
        ("Builders", "Testers", "Meme team", "Lore keepers"),
        event_type="challenge",
        reward=8,
        stakes="Teams update live as people join.",
    ),
    EventSpec(
        "Boss Fight",
        "A bug boss appears in chat. Choose your role.",
        ("Tank the errors", "Patch the bug", "Write tests", "Ship it"),
        event_type="challenge",
        reward=12,
        stakes="Every role matters. Join once and coordinate in chat.",
    ),
    EventSpec(
        "Memory Flash",
        "Which command shows the richest users?",
        ("-wallet", "-leaderboard", "-shop", "-daily"),
        correct_index=1,
        event_type="quiz",
        reward=20,
        success_text="Economy memory confirmed.",
        failure_text="That command does something else.",
    ),
    EventSpec(
        "Loot Crate",
        "A crate lands in the events channel. One latch has coins inside.",
        ("Left latch", "Middle latch", "Right latch"),
        correct_index=1,
        event_type="mystery",
        reward=35,
        success_text="The crate bursts open with coins.",
        failure_text="The latch snaps shut. No loot there.",
    ),
    EventSpec(
        "Hot Take Meter",
        "Pick the take you are willing to defend for one minute.",
        ("Tabs beat spaces", "Spaces beat tabs", "Both are fine", "Depends on the repo"),
        stakes="The majority take becomes the debate topic.",
    ),
)


class ServerManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = ServerSettings()
        self.game_store = GameStore()
        self.min_interval = _read_int_env("EVENT_MIN_INTERVAL_MINUTES", 90)
        self.max_interval = max(_read_int_env("EVENT_MAX_INTERVAL_MINUTES", 240), self.min_interval)
        self._next_event_at: dict[int, datetime] = {}
        self._event_bags: dict[int, Deque[EventSpec]] = {}
        self.random_events_loop.start()

    def cog_unload(self) -> None:
        self.random_events_loop.cancel()

    @commands.command(name="serverinfo", aliases=["modinfo"])
    async def server_info(self, ctx: commands.Context) -> None:
        await ctx.send(SERVER_INFO_MESSAGE)

    @commands.command(name="eventsinfo")
    async def events_info(self, ctx: commands.Context) -> None:
        await ctx.send(EVENTS_INFO_MESSAGE)

    @commands.command(name="clear", aliases=["purge"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear_messages(self, ctx: commands.Context, amount: int) -> None:
        if amount < 1 or amount > 100:
            await ctx.send("Usage: `-clear <1-100>`")
            return

        deleted = await ctx.channel.purge(
            limit=amount + 1,
            reason=f"Messages cleared by {ctx.author} ({ctx.author.id})",
        )
        await ctx.send(f"Deleted `{max(len(deleted) - 1, 0)}` message(s).", delete_after=5)

    @commands.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if not _can_moderate(ctx, member):
            await ctx.send("You cannot moderate that member.")
            return

        await member.kick(reason=_audit_reason(ctx, reason))
        await ctx.send(f"Kicked `{member}`. Reason: {reason}")

    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if not _can_moderate(ctx, member):
            await ctx.send("You cannot moderate that member.")
            return

        await member.ban(delete_message_seconds=0, reason=_audit_reason(ctx, reason))
        await ctx.send(f"Banned `{member}`. Reason: {reason}")

    @commands.command(name="seteventchannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(send_messages=True)
    async def set_event_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        if not _bot_can_send(channel):
            await ctx.send("I cannot send messages in that channel.")
            return

        self.settings.set_event_channel_id(ctx.guild.id, channel.id)
        self._schedule_next_event(ctx.guild.id)
        await ctx.send(f"Random events channel set to {channel.mention}.")

    @commands.command(name="eventson")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def events_on(self, ctx: commands.Context) -> None:
        self.settings.set_events_enabled(ctx.guild.id, True)
        self._schedule_next_event(ctx.guild.id)
        await ctx.send("Random events enabled.")

    @commands.command(name="eventsoff")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def events_off(self, ctx: commands.Context) -> None:
        self.settings.set_events_enabled(ctx.guild.id, False)
        self._next_event_at.pop(ctx.guild.id, None)
        await ctx.send("Random events disabled.")

    @commands.command(name="eventnow")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def event_now(self, ctx: commands.Context) -> None:
        channel = self._event_channel(ctx.guild)
        if channel is None:
            await ctx.send("Set an events channel first with `-seteventchannel #channel`.")
            return

        if not await self._send_event(ctx.guild.id, channel):
            await ctx.send("I cannot send messages in the configured events channel.")
            return

        self._schedule_next_event(ctx.guild.id)
        await ctx.send(f"Random event sent to {channel.mention}.", delete_after=5)

    @tasks.loop(minutes=1)
    async def random_events_loop(self) -> None:
        now = datetime.now(UTC)
        for guild in self.bot.guilds:
            if not self.settings.events_enabled(guild.id):
                continue

            channel = self._event_channel(guild)
            if channel is None:
                continue

            next_event_at = self._next_event_at.get(guild.id)
            if next_event_at is None:
                self._schedule_next_event(guild.id)
                continue

            if now < next_event_at:
                continue

            await self._send_event(guild.id, channel)
            self._schedule_next_event(guild.id)

    @random_events_loop.before_loop
    async def before_random_events_loop(self) -> None:
        await self.bot.wait_until_ready()

    def _event_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = self.settings.get_event_channel_id(guild.id)
        if channel_id is None:
            return None

        channel = guild.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    def _schedule_next_event(self, guild_id: int) -> None:
        minutes = random.randint(self.min_interval, self.max_interval)
        self._next_event_at[guild_id] = datetime.now(UTC) + timedelta(minutes=minutes)

    async def _send_event(self, guild_id: int, channel: discord.TextChannel) -> bool:
        return await _send_event(channel, self._next_event(guild_id), self._game_store(), guild_id)

    def _game_store(self) -> GameStore:
        games_cog = self.bot.get_cog("GamesCog")
        if isinstance(games_cog, GamesCog):
            return games_cog.store

        return self.game_store

    def _next_event(self, guild_id: int) -> EventSpec:
        bag = self._event_bags.get(guild_id)
        if not bag:
            events = list(RANDOM_EVENTS)
            random.shuffle(events)
            bag = deque(events)
            self._event_bags[guild_id] = bag

        return bag.popleft()


def _can_moderate(ctx: commands.Context, member: discord.Member) -> bool:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        return False

    if member == ctx.author or member == ctx.guild.owner:
        return False

    bot_member = ctx.guild.me
    if bot_member is not None and member.top_role >= bot_member.top_role:
        return False

    if ctx.author != ctx.guild.owner and member.top_role >= ctx.author.top_role:
        return False

    return True


def _audit_reason(ctx: commands.Context, reason: str) -> str:
    return f"{reason} | by {ctx.author} ({ctx.author.id})"


async def _send_event(
    channel: discord.TextChannel,
    event: EventSpec,
    game_store: GameStore,
    guild_id: int,
) -> bool:
    if not _bot_can_send(channel):
        return False

    use_embeds = _bot_can_embed(channel)
    view = InteractiveEventView(event, game_store, guild_id, use_embeds=use_embeds)

    try:
        message = await channel.send(**_event_payload(event, view, use_embeds=use_embeds))
    except discord.HTTPException:
        LOGGER.exception("Failed to send random event to channel %s", channel.id)
        return False

    view.message = message
    return True


class InteractiveEventView(discord.ui.View):
    def __init__(self, event: EventSpec, game_store: GameStore, guild_id: int, *, use_embeds: bool = True):
        super().__init__(timeout=900)
        self.event = event
        self.game_store = game_store
        self.guild_id = guild_id
        self.use_embeds = use_embeds
        self.message: discord.Message | None = None
        self.votes: dict[int, int] = {}
        self.counts = [0 for _ in event.options]
        self.participants: dict[int, set[int]] = {index: set() for index in range(len(event.options))}
        self.user_labels: dict[int, str] = {}
        self.rewarded_users: set[int] = set()
        self.mystery_picks: dict[int, int] = {}
        self.solved_by: int | None = None
        self.closed = False

        for index, option in enumerate(event.options):
            button = discord.ui.Button(label=option, style=_button_style_for(event, index))
            button.callback = self._callback_for(index)
            self.add_item(button)

    def _callback_for(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            if self.closed:
                await interaction.response.send_message("Este evento ja terminou.", ephemeral=True)
                return

            if self.event.event_type == "race":
                await self._handle_race(interaction)
                return

            if self.event.event_type == "challenge":
                await self._handle_challenge(interaction, index)
                return

            if self.event.event_type == "mystery":
                await self._handle_mystery(interaction, index)
                return

            if self.event.correct_index is not None:
                await self._handle_quiz(interaction, index)
                return

            await self._handle_vote(interaction, index)

        return callback

    async def _handle_vote(self, interaction: discord.Interaction, index: int) -> None:
        previous = self.votes.get(interaction.user.id)
        if previous is not None:
            self.counts[previous] = max(self.counts[previous] - 1, 0)

        self.votes[interaction.user.id] = index
        self.counts[index] += 1
        self._remember_user(interaction.user)
        await self._edit_interaction(interaction)

    async def _handle_quiz(self, interaction: discord.Interaction, index: int) -> None:
        if index != self.event.correct_index:
            await interaction.response.send_message(
                self.event.failure_text or "Resposta errada. Tenta outra vez.",
                ephemeral=True,
            )
            return

        if self.solved_by is None:
            self.solved_by = interaction.user.id
            self._remember_user(interaction.user)
            self._disable_buttons()

            reward_line = self._award_reward(interaction.user.id)
            await self._edit_interaction(interaction, winner=interaction.user.mention, reward_line=reward_line)
            return

        await interaction.response.send_message("Este quiz ja foi resolvido.", ephemeral=True)

    async def _handle_race(self, interaction: discord.Interaction) -> None:
        if self.solved_by is not None:
            await interaction.response.send_message("Este evento ja tem vencedor.", ephemeral=True)
            return

        self.solved_by = interaction.user.id
        self._remember_user(interaction.user)
        self._disable_buttons()

        reward_line = self._award_reward(interaction.user.id)
        await self._edit_interaction(interaction, winner=interaction.user.mention, reward_line=reward_line)

    async def _handle_challenge(self, interaction: discord.Interaction, index: int) -> None:
        previous = self.votes.get(interaction.user.id)
        if previous is not None:
            self.participants[previous].discard(interaction.user.id)
            self.counts[previous] = max(self.counts[previous] - 1, 0)

        first_join = interaction.user.id not in self.rewarded_users
        self.votes[interaction.user.id] = index
        self.participants[index].add(interaction.user.id)
        self.counts[index] += 1
        self._remember_user(interaction.user)

        reward_line = self._award_reward_once(interaction.user.id) if first_join else None
        await self._edit_interaction(interaction)

        detail = f"Entraste em `{self.event.options[index]}`."
        if reward_line is not None:
            detail = f"{detail} {reward_line}"
        await interaction.followup.send(detail, ephemeral=True)

    async def _handle_mystery(self, interaction: discord.Interaction, index: int) -> None:
        if interaction.user.id in self.mystery_picks:
            await interaction.response.send_message("Ja tentaste abrir uma porta neste evento.", ephemeral=True)
            return

        self.mystery_picks[interaction.user.id] = index
        self.counts[index] += 1
        self._remember_user(interaction.user)

        if index != self.event.correct_index:
            await self._edit_interaction(interaction)
            await interaction.followup.send(
                self.event.failure_text or "Nao havia premio nessa escolha.",
                ephemeral=True,
            )
            return

        self.solved_by = interaction.user.id
        self._disable_buttons()
        reward_line = self._award_reward(interaction.user.id)
        await self._edit_interaction(interaction, winner=interaction.user.mention, reward_line=reward_line)

    def _award_reward(self, user_id: int) -> str | None:
        if self.event.reward <= 0:
            return None

        balance = self.game_store.add_coins(self.guild_id, user_id, self.event.reward)
        return f"Recompensa: {format_coins(self.event.reward)}. Saldo: {format_coins(balance)}"

    def _award_reward_once(self, user_id: int) -> str | None:
        if user_id in self.rewarded_users:
            return None

        self.rewarded_users.add(user_id)
        return self._award_reward(user_id)

    async def _edit_interaction(
        self,
        interaction: discord.Interaction,
        *,
        winner: str | None = None,
        reward_line: str | None = None,
    ) -> None:
        await interaction.response.edit_message(
            **_event_payload(
                self.event,
                self,
                counts=self.counts,
                winner=winner,
                reward_line=reward_line,
                participants=self.participants,
                user_labels=self.user_labels,
                closed=self.closed,
                use_embeds=self.use_embeds,
            )
        )

    async def on_timeout(self) -> None:
        self.closed = True
        self._disable_buttons()

        if self.message is None:
            return

        try:
            await self.message.edit(
                **_event_payload(
                    self.event,
                    self,
                    counts=self.counts,
                    participants=self.participants,
                    user_labels=self.user_labels,
                    closed=True,
                    use_embeds=self.use_embeds,
                )
            )
        except discord.HTTPException:
            LOGGER.exception("Failed to close timed out random event message %s", self.message.id)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        LOGGER.exception("Random event interaction failed on item %s", item, exc_info=error)
        message = "A interacao falhou do lado do bot. Tenta outra vez daqui a pouco."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            LOGGER.exception("Failed to report random event interaction error")

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def _remember_user(self, user: discord.User | discord.Member) -> None:
        display_name = getattr(user, "display_name", None) or getattr(user, "global_name", None) or user.name
        self.user_labels[user.id] = str(display_name)


def _event_payload(
    event: EventSpec,
    view: discord.ui.View,
    *,
    counts: list[int] | None = None,
    winner: str | None = None,
    reward_line: str | None = None,
    participants: dict[int, set[int]] | None = None,
    user_labels: dict[int, str] | None = None,
    closed: bool = False,
    use_embeds: bool = True,
) -> dict[str, object]:
    if not use_embeds:
        return {
            "content": _render_event(
                event,
                counts=counts,
                winner=winner,
                reward_line=reward_line,
                participants=participants,
                user_labels=user_labels,
                closed=closed,
            ),
            "view": view,
        }

    return {
        "content": f"Random event: **{event.title}**",
        "embed": _build_event_embed(
            event,
            counts=counts,
            winner=winner,
            reward_line=reward_line,
            participants=participants,
            user_labels=user_labels,
            closed=closed,
        ),
        "view": view,
    }


def _render_event(
    event: EventSpec,
    counts: list[int] | None = None,
    winner: str | None = None,
    reward_line: str | None = None,
    participants: dict[int, set[int]] | None = None,
    user_labels: dict[int, str] | None = None,
    closed: bool = False,
) -> str:
    lines = [f"Random event: {event.title}", event.prompt]
    if event.stakes:
        lines.append(f"Stakes: {event.stakes}")
    if closed:
        lines.append("Status: closed.")
    lines.append("")

    if event.event_type == "race":
        reward = f" Reward: {format_coins(event.reward)}." if event.reward else ""
        lines.append(f"First valid click wins.{reward}")
        if winner is not None:
            success = f" {event.success_text}" if event.success_text else ""
            lines.append(f"{winner} won the race.{success}")
        if reward_line is not None:
            lines.append(reward_line)
        return "\n".join(lines)

    lines.extend(
        _event_board_lines(
            event,
            counts=counts,
            participants=participants,
            user_labels=user_labels,
        )
    )

    if event.event_type == "challenge":
        lines.append("")
        lines.append("Join a lane, then continue the prompt in chat.")
        return "\n".join(lines)

    if event.event_type == "mystery":
        lines.append("")
        lines.append("Each user gets one attempt.")
        if winner is not None and event.correct_index is not None:
            answer = event.options[event.correct_index]
            success = f" {event.success_text}" if event.success_text else ""
            lines.append(f"{winner} opened the right choice: {answer}.{success}")
        if reward_line is not None:
            lines.append(reward_line)
        return "\n".join(lines)

    if event.correct_index is None:
        return "\n".join(lines)

    lines.append("")
    lines.append("Choose the correct answer.")
    if winner is not None:
        answer = event.options[event.correct_index]
        success = f" {event.success_text}" if event.success_text else ""
        lines.append(f"{winner} got it right. Answer: {answer}.{success}")
    if reward_line is not None:
        lines.append(reward_line)

    return "\n".join(lines)


def _build_event_embed(
    event: EventSpec,
    *,
    counts: list[int] | None = None,
    winner: str | None = None,
    reward_line: str | None = None,
    participants: dict[int, set[int]] | None = None,
    user_labels: dict[int, str] | None = None,
    closed: bool = False,
) -> discord.Embed:
    description = event.prompt
    if event.stakes:
        description = f"{description}\n\n{event.stakes}"
    if closed:
        description = f"{description}\n\nStatus: closed."

    embed = discord.Embed(
        title=event.title,
        description=description,
        color=_event_color(event),
    )
    embed.add_field(
        name=_board_title(event),
        value="\n".join(
            _event_board_lines(
                event,
                counts=counts,
                participants=participants,
                user_labels=user_labels,
            )
        )
        or "No activity yet.",
        inline=False,
    )

    result = _event_result_text(event, winner=winner, reward_line=reward_line)
    if result:
        embed.add_field(name="Result", value=result, inline=False)

    embed.set_footer(text=_event_footer(event))
    return embed


def _event_board_lines(
    event: EventSpec,
    *,
    counts: list[int] | None = None,
    participants: dict[int, set[int]] | None = None,
    user_labels: dict[int, str] | None = None,
) -> list[str]:
    counts = counts or [0 for _ in event.options]
    total = sum(counts)
    lines: list[str] = []

    if event.event_type == "challenge":
        for index, option in enumerate(event.options):
            count = counts[index] if index < len(counts) else 0
            preview = _participant_preview((participants or {}).get(index, set()), user_labels or {})
            suffix = f" - {preview}" if preview else ""
            lines.append(f"{option}: {count} participant(s){suffix}")
        return lines

    if event.event_type == "mystery":
        for index, option in enumerate(event.options):
            count = counts[index] if index < len(counts) else 0
            lines.append(f"{option}: {count} attempt(s)")
        return lines

    if event.event_type == "race":
        reward = f" Reward: {format_coins(event.reward)}." if event.reward else ""
        return [f"First valid click wins.{reward}"]

    if event.correct_index is not None:
        reward = f" Reward: {format_coins(event.reward)}." if event.reward else ""
        return [f"Answer the prompt with the buttons.{reward}"]

    for index, option in enumerate(event.options):
        count = counts[index] if index < len(counts) else 0
        percentage = round((count / total) * 100) if total else 0
        lines.append(f"{option}: {count} vote(s) {_progress_bar(count, total)} {percentage}%")

    return lines


def _event_result_text(event: EventSpec, *, winner: str | None, reward_line: str | None) -> str:
    lines: list[str] = []

    if winner is not None:
        if event.event_type == "race":
            success = f" {event.success_text}" if event.success_text else ""
            lines.append(f"{winner} won the race.{success}")
        elif event.event_type == "mystery" and event.correct_index is not None:
            success = f" {event.success_text}" if event.success_text else ""
            lines.append(f"{winner} opened `{event.options[event.correct_index]}`.{success}")
        elif event.correct_index is not None:
            success = f" {event.success_text}" if event.success_text else ""
            lines.append(f"{winner} got it right: `{event.options[event.correct_index]}`.{success}")

    if reward_line:
        lines.append(reward_line)

    return "\n".join(lines)


def _participant_preview(user_ids: set[int], user_labels: dict[int, str]) -> str:
    if not user_ids:
        return ""

    names = [user_labels.get(user_id, f"User {user_id}") for user_id in sorted(user_ids)]
    preview = ", ".join(names[:5])
    remaining = len(names) - 5
    if remaining > 0:
        preview = f"{preview}, +{remaining} more"

    return preview


def _progress_bar(count: int, total: int, width: int = 10) -> str:
    if total <= 0:
        filled = 0
    else:
        filled = round((count / total) * width)

    return f"[{'#' * filled}{'-' * (width - filled)}]"


def _button_style_for(event: EventSpec, index: int) -> discord.ButtonStyle:
    if event.event_type == "race":
        return discord.ButtonStyle.success
    if event.event_type == "mystery":
        return discord.ButtonStyle.secondary
    if event.event_type == "challenge":
        return discord.ButtonStyle.primary
    if event.correct_index is not None:
        return discord.ButtonStyle.secondary

    styles = (
        discord.ButtonStyle.primary,
        discord.ButtonStyle.success,
        discord.ButtonStyle.secondary,
        discord.ButtonStyle.danger,
    )
    return styles[index % len(styles)]


def _event_color(event: EventSpec) -> discord.Color:
    if event.event_type == "race":
        return discord.Color.gold()
    if event.event_type == "challenge":
        return discord.Color.green()
    if event.event_type == "mystery":
        return discord.Color.dark_teal()
    if event.correct_index is not None:
        return discord.Color.purple()
    return discord.Color.blurple()


def _board_title(event: EventSpec) -> str:
    if event.event_type == "challenge":
        return "Teams"
    if event.event_type == "mystery":
        return "Attempts"
    if event.correct_index is not None:
        return "Quiz"
    if event.event_type == "race":
        return "Race"
    return "Live Board"


def _event_footer(event: EventSpec) -> str:
    if event.event_type == "race":
        return "Fastest click wins."
    if event.event_type == "challenge":
        return "Pick a lane and continue in chat."
    if event.event_type == "mystery":
        return "One attempt per user."
    if event.correct_index is not None:
        return "Wrong answers are private."
    return "Votes can be changed while the event is open."


def _bot_can_send(channel: discord.TextChannel) -> bool:
    bot_member = channel.guild.me
    if bot_member is None:
        return False

    permissions = channel.permissions_for(bot_member)
    return permissions.view_channel and permissions.send_messages


def _bot_can_embed(channel: discord.TextChannel) -> bool:
    bot_member = channel.guild.me
    if bot_member is None:
        return False

    return channel.permissions_for(bot_member).embed_links


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        return max(int(raw), 1)
    except ValueError:
        return default
