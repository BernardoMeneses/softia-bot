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

from .messages import EVENTS_INFO_MESSAGE, SERVER_INFO_MESSAGE
from .server_settings import ServerSettings


LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class EventSpec:
    title: str
    prompt: str
    options: tuple[str, ...]
    correct_index: int | None = None


RANDOM_EVENTS = (
    EventSpec(
        "Quick Poll",
        "Pick the server mood for the next hour.",
        ("Focus mode", "Chaos mode", "Music mode"),
    ),
    EventSpec(
        "This or That",
        "What is better for late-night work?",
        ("Dark mode", "Light mode"),
    ),
    EventSpec(
        "Server Quiz",
        "What has keys but no locks?",
        ("Piano", "Map", "Clock"),
        correct_index=0,
    ),
    EventSpec(
        "Mini Challenge",
        "Choose a challenge for the chat.",
        ("5-word story", "Project pitch", "Best shortcut"),
    ),
    EventSpec(
        "Debate Drop",
        "Working with music is...",
        ("Overrated", "Underrated", "Depends"),
    ),
    EventSpec(
        "Server Quest",
        "What should people do now?",
        ("Share a useful tip", "Tag someone helpful", "Pitch a new feature"),
    ),
    EventSpec(
        "Would You Rather",
        "Pick the server rule for today.",
        ("No context memes", "Only serious answers", "Wrong answers only"),
    ),
    EventSpec(
        "Trivia Drop",
        "Which planet is known as the Red Planet?",
        ("Mars", "Venus", "Jupiter"),
        correct_index=0,
    ),
    EventSpec(
        "Speed Vote",
        "What should the next community activity be?",
        ("Game night", "Code sprint", "Movie watch"),
    ),
    EventSpec(
        "Emoji Trial",
        "Which reaction should represent 'approved' today?",
        ("Green check", "Fire", "Crown"),
    ),
    EventSpec(
        "Logic Check",
        "What comes next: 2, 4, 8, 16, ?",
        ("24", "32", "64"),
        correct_index=1,
    ),
    EventSpec(
        "Roleplay Prompt",
        "Choose the scenario for a 3-message improv chain.",
        ("Space station", "Secret agency", "Startup pitch"),
    ),
)


class ServerManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = ServerSettings()
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
        return await _send_event(channel, self._next_event(guild_id))

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


async def _send_event(channel: discord.TextChannel, event: EventSpec) -> bool:
    if not _bot_can_send(channel):
        return False

    try:
        await channel.send(_render_event(event), view=InteractiveEventView(event))
    except discord.HTTPException:
        LOGGER.exception("Failed to send random event to channel %s", channel.id)
        return False

    return True


class InteractiveEventView(discord.ui.View):
    def __init__(self, event: EventSpec):
        super().__init__(timeout=900)
        self.event = event
        self.votes: dict[int, int] = {}
        self.counts = [0 for _ in event.options]
        self.solved_by: int | None = None

        for index, option in enumerate(event.options):
            button = discord.ui.Button(label=option, style=discord.ButtonStyle.primary)
            button.callback = self._callback_for(index)
            self.add_item(button)

    def _callback_for(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
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
        await interaction.response.edit_message(content=_render_event(self.event, self.counts), view=self)

    async def _handle_quiz(self, interaction: discord.Interaction, index: int) -> None:
        if index != self.event.correct_index:
            await interaction.response.send_message("Wrong answer. Try again.", ephemeral=True)
            return

        if self.solved_by is None:
            self.solved_by = interaction.user.id
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            await interaction.response.edit_message(
                content=_render_event(self.event, winner=interaction.user.mention),
                view=self,
            )
            return

        await interaction.response.send_message("This quiz was already solved.", ephemeral=True)


def _render_event(
    event: EventSpec,
    counts: list[int] | None = None,
    winner: str | None = None,
) -> str:
    lines = [f"Random event: {event.title}", event.prompt, ""]

    if event.correct_index is None:
        for index, option in enumerate(event.options):
            count = counts[index] if counts is not None else 0
            lines.append(f"{option}: {count} vote(s)")
        return "\n".join(lines)

    lines.append("Choose the correct answer.")
    if winner is not None:
        answer = event.options[event.correct_index]
        lines.append(f"{winner} got it right. Answer: {answer}")

    return "\n".join(lines)


def _bot_can_send(channel: discord.TextChannel) -> bool:
    bot_member = channel.guild.me
    if bot_member is None:
        return False

    permissions = channel.permissions_for(bot_member)
    return permissions.view_channel and permissions.send_messages


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        return max(int(raw), 1)
    except ValueError:
        return default
