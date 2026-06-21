from __future__ import annotations

import hashlib
import logging
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Deque

import discord
from discord.ext import commands

from .messages import AUDIT_INFO_MESSAGE
from .server_settings import ServerSettings


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MessageRecord:
    message_id: int
    channel_id: int
    created_at: datetime


@dataclass(frozen=True)
class ImageRecord:
    image_hash: str
    message_id: int
    channel_id: int
    created_at: datetime


class SpamGuardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = ServerSettings()
        self.message_limit = _read_int_env("SPAM_MESSAGE_LIMIT", 6)
        self.message_window = _read_int_env("SPAM_WINDOW_SECONDS", 8)
        self.image_channel_limit = _read_int_env("SPAM_IMAGE_CHANNEL_LIMIT", 3)
        self.image_window = _read_int_env("SPAM_IMAGE_WINDOW_SECONDS", 180)
        self.image_max_bytes = _read_int_env("SPAM_IMAGE_MAX_BYTES", 8 * 1024 * 1024)
        self.ban_delete_seconds = _read_int_env("SPAM_BAN_DELETE_SECONDS", 3600)
        self._messages: dict[tuple[int, int], Deque[MessageRecord]] = defaultdict(deque)
        self._images: dict[tuple[int, int, str], Deque[ImageRecord]] = defaultdict(deque)
        self._moderating: set[tuple[int, int]] = set()

    @commands.command(name="auditinfo", aliases=["spaminfo"])
    async def audit_info(self, ctx: commands.Context) -> None:
        await ctx.send(AUDIT_INFO_MESSAGE)

    @commands.command(name="auditon", aliases=["spamon"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def audit_on(self, ctx: commands.Context) -> None:
        self.settings.set_spam_guard_enabled(ctx.guild.id, True)
        await ctx.send("Anti-spam audit enabled.")

    @commands.command(name="auditoff", aliases=["spamoff"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def audit_off(self, ctx: commands.Context) -> None:
        self.settings.set_spam_guard_enabled(ctx.guild.id, False)
        await ctx.send("Anti-spam audit disabled.")

    async def audit_message(self, message: discord.Message) -> bool:
        if message.guild is None or message.author.bot:
            return False

        if not self.settings.spam_guard_enabled(message.guild.id):
            return False

        if not isinstance(message.author, discord.Member) or _is_exempt(message.author):
            return False

        key = (message.guild.id, message.author.id)
        if key in self._moderating:
            return True

        if await self._audit_message_burst(message):
            return True

        return await self._audit_repeated_images(message)

    async def _audit_message_burst(self, message: discord.Message) -> bool:
        key = (message.guild.id, message.author.id)
        now = datetime.now(UTC)
        records = self._messages[key]
        records.append(MessageRecord(message.id, message.channel.id, now))
        _trim_records(records, now - timedelta(seconds=self.message_window))

        if len(records) < self.message_limit:
            return False

        reason = f"automatic anti-spam: {len(records)} messages in {self.message_window}s"
        await self._moderate_user(message, list(records), reason)
        records.clear()
        return True

    async def _audit_repeated_images(self, message: discord.Message) -> bool:
        if not message.attachments:
            return False

        now = datetime.now(UTC)
        for attachment in message.attachments:
            image_hash = await _attachment_image_hash(attachment, self.image_max_bytes)
            if image_hash is None:
                continue

            key = (message.guild.id, message.author.id, image_hash)
            records = self._images[key]
            records.append(ImageRecord(image_hash, message.id, message.channel.id, now))
            _trim_records(records, now - timedelta(seconds=self.image_window))

            distinct_channels = {record.channel_id for record in records}
            if len(distinct_channels) < self.image_channel_limit:
                continue

            reason = (
                "automatic anti-spam: repeated same image in "
                f"{len(distinct_channels)} channels"
            )
            message_records = [
                MessageRecord(record.message_id, record.channel_id, record.created_at)
                for record in records
            ]
            await self._moderate_user(message, message_records, reason)
            records.clear()
            return True

        return False

    async def _moderate_user(
        self,
        message: discord.Message,
        records: list[MessageRecord],
        reason: str,
    ) -> None:
        assert message.guild is not None
        assert isinstance(message.author, discord.Member)

        key = (message.guild.id, message.author.id)
        self._moderating.add(key)
        try:
            await _delete_records(message.guild, records, reason)

            if not _bot_can_ban(message.guild, message.author):
                await _safe_notify(message.channel, f"Spam detected from `{message.author}`, but I cannot ban them.")
                return

            await message.guild.ban(
                message.author,
                delete_message_seconds=self.ban_delete_seconds,
                reason=reason,
            )
            await _safe_notify(message.channel, f"Banned `{message.author}` for spam.")
        except discord.HTTPException:
            LOGGER.exception("Failed to moderate spam for user %s", message.author.id)
        finally:
            self._moderating.discard(key)


async def _attachment_image_hash(attachment: discord.Attachment, max_bytes: int) -> str | None:
    if not _looks_like_image(attachment):
        return None

    if attachment.size > max_bytes:
        return _fallback_attachment_hash(attachment)

    try:
        payload = await attachment.read(use_cached=True)
    except discord.HTTPException:
        return _fallback_attachment_hash(attachment)

    return hashlib.sha256(payload).hexdigest()


def _looks_like_image(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    filename = attachment.filename.lower()
    return filename.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))


def _fallback_attachment_hash(attachment: discord.Attachment) -> str:
    fingerprint = f"{attachment.filename.lower()}:{attachment.size}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


async def _delete_records(guild: discord.Guild, records: list[MessageRecord], reason: str) -> None:
    seen: set[tuple[int, int]] = set()
    for record in records:
        key = (record.channel_id, record.message_id)
        if key in seen:
            continue
        seen.add(key)

        channel = guild.get_channel(record.channel_id)
        if not isinstance(channel, discord.TextChannel):
            continue

        try:
            await channel.get_partial_message(record.message_id).delete(reason=reason)
        except (discord.NotFound, discord.Forbidden):
            continue
        except discord.HTTPException:
            LOGGER.exception("Failed to delete spam message %s", record.message_id)


async def _safe_notify(channel: discord.abc.Messageable, content: str) -> None:
    try:
        await channel.send(content)
    except discord.HTTPException:
        LOGGER.exception("Failed to send spam moderation notice")


def _bot_can_ban(guild: discord.Guild, member: discord.Member) -> bool:
    bot_member = guild.me
    if bot_member is None:
        return False

    permissions = bot_member.guild_permissions
    return permissions.ban_members and member.top_role < bot_member.top_role


def _is_exempt(member: discord.Member) -> bool:
    permissions = member.guild_permissions
    return (
        member == member.guild.owner
        or permissions.administrator
        or permissions.manage_guild
        or permissions.manage_messages
        or permissions.ban_members
    )


def _trim_records(records: Deque[MessageRecord] | Deque[ImageRecord], cutoff: datetime) -> None:
    while records and records[0].created_at < cutoff:
        records.popleft()


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        return max(int(raw), 1)
    except ValueError:
        return default
