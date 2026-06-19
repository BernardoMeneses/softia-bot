from __future__ import annotations

import asyncio
import io
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

import discord
from discord.ext import commands
from openai import OpenAI, OpenAIError

from .discord_utils import send_text
from .messages import CHAT_INFO_MESSAGE


class ChatError(RuntimeError):
    """Raised when an OpenAI chat request cannot be completed."""


SYSTEM_PROMPT = (
    "Es o Softia, um bot generico de conversa dentro de um servidor Discord. "
    "Responde de forma clara, util e em portugues europeu quando o utilizador escrever em portugues."
)


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class ChatSession:
    user_id: int
    channel_id: int
    username: str
    started_at: datetime
    model: str
    turns: list[ChatTurn] = field(default_factory=list)
    openai_input: list[dict[str, str]] = field(default_factory=list)


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        self.max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "800"))
        self._client: OpenAI | None = None
        self._sessions: dict[tuple[int, int], ChatSession] = {}

    @commands.command(name="chatinfo")
    async def chat_info(self, ctx: commands.Context) -> None:
        await ctx.send(CHAT_INFO_MESSAGE)

    @commands.command(name="chat")
    async def chat(self, ctx: commands.Context, *, prompt: str = "") -> None:
        if not self._has_api_key():
            await ctx.send("Define `OPENAI_API_KEY` para usar o modo chat.")
            return

        session = self._get_or_create_session(ctx)
        await ctx.send("Modo chat ativo. Escreve mensagens normalmente ou usa `-abortchat` para sair.")

        prompt = prompt.strip()
        if prompt:
            await self._handle_prompt(ctx, session, prompt)

    @commands.command(name="abortchat")
    async def abort_chat(self, ctx: commands.Context) -> None:
        session = self._sessions.pop(_session_key(ctx.author.id, ctx.channel.id), None)
        if session is None:
            await ctx.send("Nao tens uma conversa ativa neste canal.")
            return

        transcript = build_transcript(session)
        file = discord.File(
            io.BytesIO(transcript.encode("utf-8")),
            filename=_transcript_filename(session),
        )
        await ctx.send("Modo chat terminado. Conversa guardada em anexo.", file=file)

    async def maybe_handle_message(self, message: discord.Message) -> bool:
        if message.author.bot:
            return False

        session = self._sessions.get(_session_key(message.author.id, message.channel.id))
        if session is None:
            return False

        if await self._is_command(message, "abortchat") or await self._is_command(message, "chat"):
            return False

        content = message.content.strip()
        if not content:
            return True

        await self._handle_prompt(message.channel, session, content)
        return True

    async def _handle_prompt(
        self,
        destination: commands.Context | discord.abc.Messageable,
        session: ChatSession,
        prompt: str,
    ) -> None:
        session.turns.append(ChatTurn("user", prompt))
        session.openai_input.append({"role": "user", "content": prompt})

        try:
            async with destination.typing():
                reply = await asyncio.to_thread(self._ask_openai, session.openai_input)
        except ChatError as exc:
            await destination.send(str(exc))
            return

        session.turns.append(ChatTurn("assistant", reply))
        session.openai_input.append({"role": "assistant", "content": reply})
        await send_text(destination.send, reply)

    def _ask_openai(self, input_items: list[dict[str, str]]) -> str:
        try:
            response = self._client_or_raise().responses.create(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=input_items,
                max_output_tokens=self.max_output_tokens,
            )
        except OpenAIError as exc:
            raise ChatError("Nao consegui obter resposta da API do OpenAI.") from exc

        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise ChatError("A API do OpenAI nao devolveu texto.")

        return output_text.strip()

    def _client_or_raise(self) -> OpenAI:
        if not self._has_api_key():
            raise ChatError("Define `OPENAI_API_KEY` para usar o modo chat.")

        if self._client is None:
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        return self._client

    def _get_or_create_session(self, ctx: commands.Context) -> ChatSession:
        key = _session_key(ctx.author.id, ctx.channel.id)
        if key not in self._sessions:
            self._sessions[key] = ChatSession(
                user_id=ctx.author.id,
                channel_id=ctx.channel.id,
                username=ctx.author.display_name,
                started_at=datetime.now(UTC),
                model=self.model,
            )
        return self._sessions[key]

    def _has_api_key(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    async def _is_command(self, message: discord.Message, command_name: str) -> bool:
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]

        content = message.content.strip()
        return any(
            content == f"{prefix}{command_name}" or content.startswith(f"{prefix}{command_name} ")
            for prefix in prefixes
        )


def build_transcript(session: ChatSession) -> str:
    lines = [
        "Softia chat transcript",
        f"User: {session.username} ({session.user_id})",
        f"Channel ID: {session.channel_id}",
        f"Model: {session.model}",
        f"Started at: {session.started_at.isoformat()}",
        "",
    ]

    for turn in session.turns:
        label = "User" if turn.role == "user" else "Softia"
        lines.append(f"{label}: {turn.content}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _session_key(user_id: int, channel_id: int) -> tuple[int, int]:
    return user_id, channel_id


def _transcript_filename(session: ChatSession) -> str:
    timestamp = session.started_at.strftime("%Y%m%d-%H%M%S")
    return f"softia-chat-{session.user_id}-{timestamp}.txt"
