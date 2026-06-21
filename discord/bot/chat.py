from __future__ import annotations

import asyncio
import io
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

import discord
from discord.ext import commands
from openai import OpenAI, OpenAIError

from .discord_utils import send_text
from .messages import CHAT_INFO_MESSAGE
from .search import SearchError, SearchResult, fallback_search


class ChatError(RuntimeError):
    """Raised when an OpenAI chat request cannot be completed."""


SYSTEM_PROMPT = (
    "You are Softia, a general-purpose Discord chat assistant. Multiple Discord users can speak "
    "in the same channel conversation, so track who said what from the speaker names in the input. "
    "Answer in the same language as the latest user unless they ask otherwise. Before answering, use "
    "the supplied web search context when it is relevant. If the web context is missing, weak, or "
    "unrelated, still give the best useful answer from reasoning and clearly say when you are unsure. "
    "Do not invent sources or claim a source says something unless it appears in the supplied context."
)

CONTINUATION_PROMPT = (
    "Continue exactly where your previous answer stopped. Do not restart, summarize, "
    "or repeat completed sections."
)

TRUNCATION_NOTICE = (
    "\n\n[A resposta ainda pode estar incompleta porque atingiu o limite configurado. "
    "Aumenta `OPENAI_MAX_OUTPUT_TOKENS` ou `CHAT_CONTINUATION_ATTEMPTS` se precisares "
    "de respostas maiores.]"
)


@dataclass
class ChatTurn:
    role: str
    content: str
    author_name: str | None = None


@dataclass
class ChatSession:
    channel_id: int
    started_by_user_id: int
    started_by_username: str
    started_at: datetime
    model: str
    turns: list[ChatTurn] = field(default_factory=list)
    openai_input: list[dict[str, str]] = field(default_factory=list)


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        self.max_output_tokens = _read_int_env("OPENAI_MAX_OUTPUT_TOKENS", 2000)
        self.continuation_attempts = _read_non_negative_int_env("CHAT_CONTINUATION_ATTEMPTS", 2)
        self.web_search_limit = _read_int_env("CHAT_WEB_SEARCH_LIMIT", 5)
        self._client: OpenAI | None = None
        self._sessions: dict[int, ChatSession] = {}

    @commands.command(name="chatinfo")
    async def chat_info(self, ctx: commands.Context) -> None:
        await ctx.send(CHAT_INFO_MESSAGE)

    @commands.command(name="chat")
    async def chat(self, ctx: commands.Context, *, prompt: str = "") -> None:
        if not self._has_api_key():
            await ctx.send("Define `OPENAI_API_KEY` para usar o modo chat.")
            return

        session = self._get_or_create_session(ctx)
        await ctx.send(
            "Modo chat ativo neste canal. Qualquer user pode participar; usa `-abortchat` para sair."
        )

        prompt = prompt.strip()
        if prompt:
            await self._handle_prompt(ctx, session, ctx.author.display_name, prompt)

    @commands.command(name="abortchat")
    async def abort_chat(self, ctx: commands.Context) -> None:
        session = self._sessions.pop(_session_key(ctx.channel.id), None)
        if session is None:
            await ctx.send("Nao existe uma conversa ativa neste canal.")
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

        session = self._sessions.get(_session_key(message.channel.id))
        if session is None:
            return False

        if await self._is_command(message, "abortchat") or await self._is_command(message, "chat"):
            return False

        content = message.content.strip()
        if not content:
            return True

        await self._handle_prompt(message.channel, session, message.author.display_name, content)
        return True

    async def _handle_prompt(
        self,
        destination: commands.Context | discord.abc.Messageable,
        session: ChatSession,
        author_name: str,
        prompt: str,
    ) -> None:
        session.turns.append(ChatTurn("user", prompt, author_name))
        search_results: list[SearchResult] = []

        try:
            async with destination.typing():
                search_results = await asyncio.to_thread(_safe_web_search, prompt, self.web_search_limit)
                model_prompt = build_model_prompt(author_name, prompt, search_results)
                session.openai_input.append({"role": "user", "content": model_prompt})
                reply = await asyncio.to_thread(self._ask_openai, session.openai_input)
        except ChatError as exc:
            reply = build_fallback_reply(exc, search_results)
            session.turns.append(ChatTurn("assistant", reply))
            await send_text(destination.send, reply)
            return

        session.turns.append(ChatTurn("assistant", reply))
        session.openai_input.append({"role": "assistant", "content": reply})
        await send_text(destination.send, reply)

    def _ask_openai(self, input_items: list[dict[str, str]]) -> str:
        client = self._client_or_raise()
        working_input = list(input_items)
        reply_parts: list[str] = []
        max_calls = self.continuation_attempts + 1

        for call_index in range(max_calls):
            try:
                response = client.responses.create(
                    model=self.model,
                    instructions=SYSTEM_PROMPT,
                    input=working_input,
                    max_output_tokens=self.max_output_tokens,
                )
            except OpenAIError as exc:
                raise ChatError("Nao consegui obter resposta da API do OpenAI.") from exc

            output_text = getattr(response, "output_text", "")
            text = output_text.strip() if output_text else ""
            if text:
                reply_parts.append(text)
                working_input.append({"role": "assistant", "content": text})

            if not response_needs_continuation(response):
                break

            if call_index == max_calls - 1:
                reply_parts.append(TRUNCATION_NOTICE)
                break

            working_input.append({"role": "user", "content": CONTINUATION_PROMPT})

        if not reply_parts:
            raise ChatError("A API do OpenAI nao devolveu texto.")

        return "\n\n".join(reply_parts).strip()

    def _client_or_raise(self) -> OpenAI:
        if not self._has_api_key():
            raise ChatError("Define `OPENAI_API_KEY` para usar o modo chat.")

        if self._client is None:
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        return self._client

    def _get_or_create_session(self, ctx: commands.Context) -> ChatSession:
        key = _session_key(ctx.channel.id)
        if key not in self._sessions:
            self._sessions[key] = ChatSession(
                channel_id=ctx.channel.id,
                started_by_user_id=ctx.author.id,
                started_by_username=ctx.author.display_name,
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
        f"Started by: {session.started_by_username} ({session.started_by_user_id})",
        f"Channel ID: {session.channel_id}",
        f"Model: {session.model}",
        f"Started at: {session.started_at.isoformat()}",
        "",
    ]

    for turn in session.turns:
        label = turn.author_name if turn.role == "user" and turn.author_name else "Softia"
        lines.append(f"{label}: {turn.content}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_model_prompt(author_name: str, prompt: str, search_results: Iterable[SearchResult]) -> str:
    return (
        f"Discord speaker: {author_name}\n"
        f"User message:\n{prompt}\n\n"
        f"{_format_web_context(search_results)}"
    )


def build_fallback_reply(error: ChatError, search_results: Iterable[SearchResult]) -> str:
    results = list(search_results)
    if not results:
        return f"{error} Tambem nao encontrei resultados web uteis para responder com seguranca."

    lines = [f"{error} Encontrei estes resultados web que podem ajudar:"]
    for index, result in enumerate(results, start=1):
        snippet = f" - {result.snippet}" if result.snippet else ""
        lines.append(f"{index}. {result.title}: {result.url}{snippet}")

    return "\n".join(lines)


def _format_web_context(search_results: Iterable[SearchResult]) -> str:
    results = list(search_results)
    if not results:
        return (
            "Web search context: no reliable results were available. "
            "Answer anyway using general reasoning, and mention uncertainty when needed."
        )

    lines = ["Web search context:"]
    for index, result in enumerate(results, start=1):
        snippet = f" - {result.snippet}" if result.snippet else ""
        lines.append(f"{index}. {result.title} ({result.url}){snippet}")

    return "\n".join(lines)


def _safe_web_search(prompt: str, limit: int) -> list[SearchResult]:
    query = _search_query_from_prompt(prompt)
    if not query:
        return []

    try:
        return fallback_search(query, limit)
    except SearchError:
        return []


def _search_query_from_prompt(prompt: str) -> str:
    return " ".join(prompt.split())[:250]


def _session_key(channel_id: int) -> int:
    return channel_id


def _transcript_filename(session: ChatSession) -> str:
    timestamp = session.started_at.strftime("%Y%m%d-%H%M%S")
    return f"softia-chat-{session.channel_id}-{timestamp}.txt"


def response_needs_continuation(response: object) -> bool:
    if getattr(response, "status", None) == "incomplete":
        return _incomplete_reason(response) in {None, "", "max_output_tokens"}

    if getattr(response, "incomplete_details", None):
        return _incomplete_reason(response) in {None, "", "max_output_tokens"}

    return False


def _incomplete_reason(response: object) -> str | None:
    details = getattr(response, "incomplete_details", None)
    if details is None:
        return None

    if isinstance(details, dict):
        reason = details.get("reason")
    else:
        reason = getattr(details, "reason", None)

    if reason is None:
        return None

    return str(reason)


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        return max(int(raw), 1)
    except ValueError:
        return default


def _read_non_negative_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        return max(int(raw), 0)
    except ValueError:
        return default
