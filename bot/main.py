from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Iterable

import discord
from discord.ext import commands
from dotenv import load_dotenv

from . import math_utils
from .chat import ChatCog
from .games import GamesCog
from .messages import BOT_SUMMARY, DEVS_MESSAGE, INFO_MESSAGE, MATH_INFO_MESSAGE
from .music import MusicCog
from .search import SearchCog
from .server_management import ServerManagementCog
from .spam_guard import SpamGuardCog


def build_bot() -> commands.Bot:
    load_dotenv()
    prefix = os.getenv("DISCORD_PREFIX", "-")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix=prefix, intents=intents, help_command=None)
    register_commands(bot)
    return bot


def register_commands(bot: commands.Bot) -> None:
    @bot.event
    async def on_ready() -> None:
        user = bot.user
        name = user.name if user else "Softia"
        logging.info("Bot ligado como %s", name)

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Faltam argumentos. Usa `-info`, `-musicinfo` ou `-mathinfo`.")
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to use that command.")
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await ctx.send(f"I am missing these permissions: `{missing}`.")
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument. Check the command usage with `-info`.")
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command can only be used inside a server.")
            return

        if isinstance(error, commands.CommandInvokeError):
            original = error.original
            if isinstance(original, discord.Forbidden):
                await ctx.send("Discord refused that action. Check my role hierarchy and channel permissions.")
                return

            if isinstance(original, discord.HTTPException):
                await ctx.send("Discord rejected that request. Try again or check the command arguments.")
                return

        logging.exception("Erro ao executar comando", exc_info=error)
        await ctx.send("Nao consegui executar esse comando.")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        spam_cog = bot.get_cog("SpamGuardCog")
        if isinstance(spam_cog, SpamGuardCog) and await spam_cog.audit_message(message):
            return

        chat_cog = bot.get_cog("ChatCog")
        if isinstance(chat_cog, ChatCog) and await chat_cog.maybe_handle_message(message):
            return

        await bot.process_commands(message)

    @bot.command(name="devs")
    async def devs(ctx: commands.Context) -> None:
        await ctx.send(DEVS_MESSAGE)

    @bot.command(name="sum")
    async def summary_or_sum(ctx: commands.Context, *args: str) -> None:
        if not args:
            await ctx.send(BOT_SUMMARY)
            return

        await _send_binary_operation(ctx, args, math_utils.add, "`-sum <num1> <num2>`")

    @bot.command(name="info")
    async def info(ctx: commands.Context) -> None:
        await ctx.send(INFO_MESSAGE)

    @bot.command(name="mathinfo")
    async def math_info(ctx: commands.Context) -> None:
        await ctx.send(MATH_INFO_MESSAGE)

    @bot.command(name="sub")
    async def subtract(ctx: commands.Context, *args: str) -> None:
        await _send_binary_operation(ctx, args, math_utils.subtract, "`-sub <num1> <num2>`")

    @bot.command(name="mult")
    async def multiply(ctx: commands.Context, *args: str) -> None:
        await _send_binary_operation(ctx, args, math_utils.multiply, "`-mult <num1> * <num2>`", "*")

    @bot.command(name="div")
    async def divide(ctx: commands.Context, *args: str) -> None:
        await _send_binary_operation(ctx, args, math_utils.divide, "`-div <num1> / <num2>`", "/")

    @bot.command(name="mod")
    async def modulo(ctx: commands.Context, *args: str) -> None:
        await _send_binary_operation(ctx, args, math_utils.modulo, "`-mod <num1> % <num2>`", "%")

    @bot.command(name="pow")
    async def power(ctx: commands.Context, *args: str) -> None:
        await _send_binary_operation(ctx, args, math_utils.power, "`-pow <num1> ^ <num2>`", "^")

    @bot.command(name="sqrt")
    async def square_root(ctx: commands.Context, *args: str) -> None:
        if len(args) not in {1, 2}:
            await ctx.send("Uso: `-sqrt <num> [grau]`")
            return

        try:
            value = math_utils.parse_number(_normalize_root_arg(args[0]))
            degree = math_utils.parse_number(args[1]) if len(args) == 2 else 2
            result = math_utils.nth_root(value, degree)
        except math_utils.MathCommandError as exc:
            await ctx.send(str(exc))
            return

        await ctx.send(f"Resultado: `{math_utils.format_number(result)}`")

    @bot.command(name="matrix")
    async def matrix(ctx: commands.Context, *, expression: str = "") -> None:
        if not expression:
            await ctx.send("Uso: `-matrix [[1,2],[3,4]] * [[5,6],[7,8]]`")
            return

        try:
            left, right = math_utils.parse_matrix_expression(expression)
            result = math_utils.matrix_multiply(left, right)
        except math_utils.MathCommandError as exc:
            await ctx.send(str(exc))
            return

        await ctx.send(f"Resultado: `{math_utils.format_matrix(result)}`")


async def _send_binary_operation(
    ctx: commands.Context,
    args: Iterable[str],
    operation: Callable[[float, float], float],
    usage: str,
    operator_token: str | None = None,
) -> None:
    try:
        left_raw, right_raw = _read_two_operands(tuple(args), usage, operator_token)
        left = math_utils.parse_number(left_raw)
        right = math_utils.parse_number(right_raw)
        result = operation(left, right)
    except math_utils.MathCommandError as exc:
        await ctx.send(str(exc))
        return

    await ctx.send(f"Resultado: `{math_utils.format_number(result)}`")


def _read_two_operands(args: tuple[str, ...], usage: str, operator_token: str | None) -> tuple[str, str]:
    values = list(args)

    if operator_token is not None:
        values = _strip_operator(values, operator_token)

    if len(values) != 2:
        raise math_utils.MathCommandError("Uso: " + usage)

    return values[0], values[1]


def _strip_operator(values: list[str], operator_token: str) -> list[str]:
    stripped: list[str] = []
    for value in values:
        if value == operator_token:
            continue
        if value.startswith(operator_token) and len(value) > 1:
            stripped.append(value[1:])
            continue
        stripped.append(value)
    return stripped


def _normalize_root_arg(value: str) -> str:
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered.startswith("raiz(") and normalized.endswith(")"):
        return normalized[5:-1]
    return normalized


async def start_bot() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Define DISCORD_TOKEN no ficheiro .env ou nas variaveis de ambiente.")

    bot = build_bot()
    async with bot:
        await bot.add_cog(MusicCog(bot))
        await bot.add_cog(SearchCog())
        await bot.add_cog(ChatCog(bot))
        await bot.add_cog(GamesCog(bot))
        await bot.add_cog(ServerManagementCog(bot))
        await bot.add_cog(SpamGuardCog(bot))
        try:
            await bot.start(token)
        except discord.LoginFailure as exc:
            raise RuntimeError("DISCORD_TOKEN invalido. Usa o Bot Token, nao o Application ID.") from exc
        except discord.PrivilegedIntentsRequired as exc:
            raise RuntimeError(
                "O bot precisa do Message Content Intent ativo no Discord Developer Portal, "
                "porque usa comandos com prefixo e le mensagens como `-info`, `-play` e `-chat`."
            ) from exc


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(start_bot())
    except RuntimeError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc
