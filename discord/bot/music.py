from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import discord
import yt_dlp
from discord.ext import commands

from .messages import MUSIC_INFO_MESSAGE


class MusicError(RuntimeError):
    """Raised when a music command cannot be completed."""


SPOTIFY_URL_RE = re.compile(r"https?://open\.spotify\.com/(track|album|playlist|artist)/[A-Za-z0-9]+")

YDL_METADATA_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
}

YDL_STREAM_OPTIONS = {
    **YDL_METADATA_OPTIONS,
    "noplaylist": True,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Track:
    title: str
    webpage_url: str
    requested_by: str
    duration: int | None = None


@dataclass
class GuildMusicState:
    queue: Deque[Track] = field(default_factory=deque)
    history: list[Track] = field(default_factory=list)
    current: Track | None = None
    loop_current: bool = False
    override_next: Track | None = None
    ignore_loop_once: bool = False
    suppress_history_once: bool = False
    text_channel: discord.abc.Messageable | None = None


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._states: dict[int, GuildMusicState] = {}

    @commands.command(name="musicinfo")
    async def music_info(self, ctx: commands.Context) -> None:
        await ctx.send(MUSIC_INFO_MESSAGE)

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *, query: str = "") -> None:
        if ctx.guild is None:
            await ctx.send("Este comando so pode ser usado num servidor.")
            return

        query = query.strip()
        if not query:
            await ctx.send("Uso: `-play <link do YouTube/Spotify ou nome da musica>`")
            return

        try:
            voice_client = await self._ensure_voice(ctx)
            state = self._state(ctx.guild.id)
            state.text_channel = ctx.channel

            async with ctx.typing():
                tracks = await resolve_tracks(query, ctx.author.display_name)

            if not tracks:
                await ctx.send("Nao encontrei nenhuma musica para esse pedido.")
                return

            idle = not voice_client.is_playing() and not voice_client.is_paused() and state.current is None
            state.queue.extend(tracks)

            if idle:
                await self._play_next(ctx.guild, voice_client)
            else:
                await ctx.send(_queued_message(tracks))
        except MusicError as exc:
            await ctx.send(str(exc))

    @commands.command(name="loop")
    async def loop(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        state = self._state(ctx.guild.id)
        state.loop_current = not state.loop_current
        status = "ligado" if state.loop_current else "desligado"
        await ctx.send(f"Loop da musica atual {status}.")

    @commands.command(name="next")
    async def next_track(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        voice_client = ctx.voice_client
        if voice_client is None or not (voice_client.is_playing() or voice_client.is_paused()):
            await ctx.send("Nao ha musica a tocar.")
            return

        state = self._state(ctx.guild.id)
        state.ignore_loop_once = True

        if voice_client.is_paused():
            voice_client.resume()
        voice_client.stop()
        await ctx.send("A passar para a proxima musica.")

    @commands.command(name="back")
    async def back(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        voice_client = ctx.voice_client
        state = self._state(ctx.guild.id)

        if not state.history:
            await ctx.send("Ainda nao ha musica anterior.")
            return

        previous = state.history.pop()
        if state.current is not None:
            state.queue.appendleft(state.current)

        state.override_next = previous
        state.ignore_loop_once = True
        state.suppress_history_once = True

        if voice_client is None:
            await ctx.send("Nao estou ligado a um canal de voz.")
            return

        if voice_client.is_playing() or voice_client.is_paused():
            if voice_client.is_paused():
                voice_client.resume()
            voice_client.stop()
        else:
            await self._play_next(ctx.guild, voice_client)

        await ctx.send(f"A voltar para `{previous.title}`.")

    @commands.command(name="queue")
    async def queue(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        state = self._state(ctx.guild.id)
        if state.current is None and not state.queue:
            await ctx.send("A queue esta vazia.")
            return

        lines = []
        if state.current is not None:
            loop_label = " (loop)" if state.loop_current else ""
            lines.append(f"A tocar: `{state.current.title}`{loop_label}")

        for index, track in enumerate(list(state.queue)[:10], start=1):
            lines.append(f"{index}. `{track.title}`")

        if len(state.queue) > 10:
            lines.append(f"... e mais {len(state.queue) - 10} musica(s).")

        await ctx.send("\n".join(lines))

    def _state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusicState()
        return self._states[guild_id]

    async def _ensure_voice(self, ctx: commands.Context) -> discord.VoiceClient:
        author_voice = getattr(ctx.author, "voice", None)
        voice_channel = getattr(author_voice, "channel", None)
        if voice_channel is None:
            raise MusicError("Entra num canal de voz antes de usar comandos de musica.")

        voice_client = ctx.voice_client
        if voice_client is None:
            return await voice_channel.connect()

        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        return voice_client

    async def _play_next(self, guild: discord.Guild, voice_client: discord.VoiceClient) -> None:
        state = self._state(guild.id)
        next_track = self._select_next_track(state)

        if next_track is None:
            state.current = None
            state.ignore_loop_once = False
            state.suppress_history_once = False
            if state.text_channel is not None:
                await state.text_channel.send("Queue terminada.")
            return

        await self._play_track(guild, voice_client, next_track)

    def _select_next_track(self, state: GuildMusicState) -> Track | None:
        finished = state.current

        if state.override_next is not None:
            next_track = state.override_next
            state.override_next = None

            if finished is not None and not state.suppress_history_once:
                state.history.append(finished)

            state.ignore_loop_once = False
            state.suppress_history_once = False
            _trim_history(state)
            return next_track

        if state.loop_current and finished is not None and not state.ignore_loop_once:
            return finished

        if finished is not None:
            state.history.append(finished)

        state.ignore_loop_once = False
        state.suppress_history_once = False
        _trim_history(state)

        if state.queue:
            return state.queue.popleft()

        return None

    async def _play_track(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient,
        track: Track,
    ) -> None:
        state = self._state(guild.id)
        state.current = track

        try:
            source = await create_audio_source(track)
        except MusicError as exc:
            state.current = None
            if state.text_channel is not None:
                await state.text_channel.send(f"Nao consegui tocar `{track.title}`: {exc}")
            await self._play_next(guild, voice_client)
            return

        def after_play(error: Exception | None) -> None:
            future = asyncio.run_coroutine_threadsafe(
                self._after_track(guild.id, error),
                self.bot.loop,
            )
            future.add_done_callback(lambda task: task.exception())

        voice_client.play(source, after=after_play)

        if state.text_channel is not None:
            await state.text_channel.send(f"A tocar agora: `{track.title}`")

    async def _after_track(self, guild_id: int, error: Exception | None) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        state = self._state(guild_id)
        if error is not None and state.text_channel is not None:
            await state.text_channel.send(f"Erro no player: `{error}`")

        voice_client = guild.voice_client
        if voice_client is None:
            state.current = None
            return

        await self._play_next(guild, voice_client)


async def resolve_tracks(query: str, requested_by: str) -> list[Track]:
    prepared_query = await asyncio.to_thread(_prepare_query, query)
    info = await asyncio.to_thread(_extract_info, prepared_query, YDL_METADATA_OPTIONS)

    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        return [_track_from_entry(entry, requested_by) for entry in entries if entry]

    return [_track_from_entry(info, requested_by)]


async def create_audio_source(track: Track) -> discord.PCMVolumeTransformer:
    info = await asyncio.to_thread(_extract_info, track.webpage_url, YDL_STREAM_OPTIONS)
    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        info = next((entry for entry in entries if entry), None)

    if not isinstance(info, dict) or not info.get("url"):
        raise MusicError("nao encontrei uma stream de audio valida.")

    executable = _ffmpeg_executable()

    try:
        source = discord.FFmpegPCMAudio(info["url"], executable=executable, **FFMPEG_OPTIONS)
    except discord.ClientException as exc:
        raise MusicError(
            "FFmpeg nao encontrado. Instala o FFmpeg ou define `FFMPEG_EXECUTABLE` "
            "com o caminho completo para `ffmpeg.exe`."
        ) from exc

    return discord.PCMVolumeTransformer(source, volume=0.6)


def _ffmpeg_executable() -> str:
    configured = os.getenv("FFMPEG_EXECUTABLE", "ffmpeg").strip() or "ffmpeg"

    if os.path.exists(configured) or shutil.which(configured):
        return configured

    if configured == "ffmpeg":
        bundled = _bundled_ffmpeg_executable()
        if bundled:
            return bundled

    raise MusicError(
        "FFmpeg nao encontrado. Instala o FFmpeg ou define `FFMPEG_EXECUTABLE` "
        "com o caminho completo para `ffmpeg.exe`."
    )


def _bundled_ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    return executable if os.path.exists(executable) else None


def _prepare_query(query: str) -> str:
    if SPOTIFY_URL_RE.search(query):
        return _spotify_to_youtube_search(query)

    if query.startswith(("http://", "https://")):
        return query

    return f"ytsearch1:{query}"


def _spotify_to_youtube_search(url: str) -> str:
    encoded_url = urllib.parse.quote(url, safe="")
    oembed_url = f"https://open.spotify.com/oembed?url={encoded_url}"

    try:
        with urllib.request.urlopen(oembed_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise MusicError("nao consegui resolver esse link Spotify.") from exc

    title = payload.get("title", "").strip()
    author = payload.get("author_name", "").strip()
    if not title:
        raise MusicError("nao consegui ler o titulo desse link Spotify.")

    search_terms = f"{title} {author}".strip()
    return f"ytsearch1:{search_terms}"


def _extract_info(query: str, options: dict[str, object]) -> dict[str, object]:
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(query, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise MusicError("nao consegui obter informacao desse audio.") from exc

    if not isinstance(info, dict):
        raise MusicError("resposta invalida do extractor de audio.")

    return info


def _track_from_entry(entry: dict[str, object], requested_by: str) -> Track:
    title = str(entry.get("title") or "Musica sem titulo")
    webpage_url = str(entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or "")

    if webpage_url and not webpage_url.startswith(("http://", "https://")):
        webpage_url = f"https://www.youtube.com/watch?v={webpage_url}"

    if not webpage_url:
        raise MusicError("nao encontrei URL para uma das musicas.")

    duration = entry.get("duration")
    return Track(
        title=title,
        webpage_url=webpage_url,
        requested_by=requested_by,
        duration=int(duration) if isinstance(duration, (int, float)) else None,
    )


def _queued_message(tracks: list[Track]) -> str:
    if len(tracks) == 1:
        return f"Adicionado a queue: `{tracks[0].title}`"

    return f"Adicionadas {len(tracks)} musicas a queue."


def _trim_history(state: GuildMusicState) -> None:
    if len(state.history) > 50:
        del state.history[:-50]
