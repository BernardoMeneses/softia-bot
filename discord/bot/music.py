from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque

import discord
import yt_dlp
from discord.ext import commands

from .messages import MUSIC_INFO_MESSAGE


class MusicError(RuntimeError):
    """Raised when a music command cannot be completed."""


URL_RE = re.compile(r"https?://[^\s<>()\]]+")
FFMPEG_EXECUTABLE_ENV = "FFMPEG_EXECUTABLE"
SPOTIFY_CLIENT_ID_ENV = "SPOTIFY_CLIENT_ID"
SPOTIFY_CLIENT_SECRET_ENV = "SPOTIFY_CLIENT_SECRET"
SPOTIFY_REFRESH_TOKEN_ENV = "SPOTIFY_REFRESH_TOKEN"
SPOTIFY_QUEUE_LIMIT_ENV = "SPOTIFY_QUEUE_LIMIT"
DEFAULT_SPOTIFY_QUEUE_LIMIT = 50
MAX_SPOTIFY_QUEUE_LIMIT = 100

YDL_METADATA_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "noplaylist": True,
    "source_address": "0.0.0.0",
}

YDL_STREAM_OPTIONS = {
    **YDL_METADATA_OPTIONS,
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


@dataclass(frozen=True)
class SpotifyLink:
    kind: str
    item_id: str
    url: str


@dataclass(frozen=True)
class SpotifyTrackSearch:
    title: str
    artists: tuple[str, ...] = ()


@dataclass
class GuildMusicState:
    queue: Deque[Track] = field(default_factory=deque)
    history: list[Track] = field(default_factory=list)
    current: Track | None = None
    loop_current: bool = False
    override_next: Track | None = None
    ignore_loop_once: bool = False
    suppress_history_once: bool = False
    suppress_queue_end_once: bool = False
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
            state.suppress_queue_end_once = False

            async with ctx.typing():
                tracks = await resolve_tracks(query, ctx.author.display_name)

            if not tracks:
                await ctx.send("Nao encontrei nenhuma musica para esse pedido.")
                return

            idle = not voice_client.is_playing() and not voice_client.is_paused() and state.current is None
            state.queue.extend(tracks)

            if idle:
                await self._play_next(ctx.guild, voice_client)
                if len(tracks) > 1:
                    await ctx.send(f"Adicionadas {len(tracks) - 1} musicas a queue.")
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

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        state = self._state(ctx.guild.id)
        voice_client = ctx.voice_client
        has_music_state = state.current is not None or bool(state.queue)

        if voice_client is None and not has_music_state:
            await ctx.send("Nao ha musica a tocar.")
            return

        _reset_music_state(state, keep_text_channel=True)
        state.suppress_queue_end_once = True

        if voice_client is not None and (voice_client.is_playing() or voice_client.is_paused()):
            if voice_client.is_paused():
                voice_client.resume()
            voice_client.stop()

        await ctx.send("Musica parada e queue limpa.")

    @commands.command(name="disconnect", aliases=["dc"])
    async def disconnect(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        state = self._state(ctx.guild.id)
        voice_client = ctx.voice_client
        _reset_music_state(state, keep_text_channel=True)
        state.suppress_queue_end_once = True

        if voice_client is None:
            await ctx.send("Nao estou ligado a um canal de voz. Queue limpa.")
            return

        await voice_client.disconnect(force=True)
        await ctx.send("Desliguei do canal de voz e limpei a queue.")

    @commands.command(name="clearqueue", aliases=["resetqueue", "clearq"])
    async def clear_queue(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        state = self._state(ctx.guild.id)
        removed = len(state.queue)
        state.queue.clear()
        state.override_next = None
        state.ignore_loop_once = False
        state.suppress_history_once = False

        if removed == 0:
            await ctx.send("A queue ja estava vazia.")
            return

        await ctx.send(f"Queue limpa. Removi {removed} musica(s).")

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
            if state.suppress_queue_end_once:
                state.suppress_queue_end_once = False
                return
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


def _reset_music_state(state: GuildMusicState, *, keep_text_channel: bool = False) -> None:
    text_channel = state.text_channel
    state.queue.clear()
    state.history.clear()
    state.current = None
    state.loop_current = False
    state.override_next = None
    state.ignore_loop_once = False
    state.suppress_history_once = False
    state.suppress_queue_end_once = False
    if keep_text_channel:
        state.text_channel = text_channel
    else:
        state.text_channel = None


async def resolve_tracks(query: str, requested_by: str) -> list[Track]:
    spotify_link = await asyncio.to_thread(_parse_spotify_link, query)
    if spotify_link is not None:
        return await asyncio.to_thread(_spotify_to_tracks, spotify_link, requested_by)

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
        raise MusicError(_ffmpeg_launch_error_message(executable, exc)) from exc

    return discord.PCMVolumeTransformer(source, volume=0.6)


def _ffmpeg_executable() -> str:
    configured = _configured_ffmpeg_executable()

    for candidate in _ffmpeg_candidates(configured):
        resolved = _resolve_ffmpeg_candidate(candidate)
        if resolved:
            return resolved

    if configured == "ffmpeg":
        bundled = _bundled_ffmpeg_executable()
        if bundled:
            return bundled

    bundled = _bundled_ffmpeg_executable()
    if bundled:
        return bundled

    raise MusicError(_ffmpeg_not_found_message(configured))


def _configured_ffmpeg_executable() -> str:
    configured = os.getenv(FFMPEG_EXECUTABLE_ENV, "ffmpeg").strip() or "ffmpeg"
    return configured.strip("\"'")


def _ffmpeg_candidates(configured: str) -> list[str]:
    expanded = os.path.expandvars(os.path.expanduser(configured))
    path = Path(expanded)
    if path.is_dir():
        return [str(path / "ffmpeg.exe"), str(path / "ffmpeg")]
    return [expanded]


def _resolve_ffmpeg_candidate(candidate: str) -> str | None:
    path = Path(candidate)
    if path.is_file():
        return str(path)

    resolved = shutil.which(candidate)
    if resolved:
        return resolved

    return None


def _ffmpeg_not_found_message(configured: str) -> str:
    return (
        "FFmpeg nao encontrado no ambiente onde o bot esta a correr. "
        f"`{FFMPEG_EXECUTABLE_ENV}` esta definido como `{configured}`. "
        "Define essa variavel com o caminho completo para `ffmpeg.exe` "
        "ou para a pasta `bin` do FFmpeg, e reinicia o bot."
    )


def _ffmpeg_launch_error_message(executable: str, error: Exception) -> str:
    return (
        "Encontrei FFmpeg, mas nao consegui arrancar o processo de audio. "
        f"Executavel: `{_short_path(executable)}`. Erro: `{error}`. "
        "Se mudaste o PATH ou instalaste FFmpeg agora, reinicia o terminal/processo do bot."
    )


def _short_path(path: str) -> str:
    resolved = Path(path)
    if resolved.name:
        return resolved.name
    return path


def _bundled_ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    return executable if os.path.exists(executable) else None


def _prepare_query(query: str) -> str:
    query = _normalize_query(query)

    url_match = URL_RE.search(query)
    if url_match:
        return _strip_url_trailing_punctuation(url_match.group(0))

    if query.startswith(("http://", "https://")):
        return query

    return f"ytsearch1:{query}"


def _normalize_query(query: str) -> str:
    normalized = query.strip()

    while len(normalized) >= 2 and (
        (normalized[0], normalized[-1]) in {("<", ">"), ("`", "`"), ('"', '"'), ("'", "'")}
    ):
        normalized = normalized[1:-1].strip()

    return normalized


def _strip_url_trailing_punctuation(url: str) -> str:
    return url.rstrip(".,;:!?")


def _parse_spotify_link(query: str) -> SpotifyLink | None:
    query = _normalize_query(query)
    url_match = URL_RE.search(query)
    if not url_match:
        return None

    url = _strip_url_trailing_punctuation(url_match.group(0))
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() != "open.spotify.com":
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[0].startswith("intl-"):
        parts = parts[1:]

    if len(parts) < 2:
        return None

    kind, item_id = parts[0], parts[1]
    if kind not in {"track", "album", "playlist", "artist"}:
        return None

    return SpotifyLink(kind=kind, item_id=item_id, url=url)


def _spotify_to_tracks(link: SpotifyLink, requested_by: str) -> list[Track]:
    searches = _spotify_track_searches(link)
    if not searches:
        raise MusicError("Nao encontrei musicas nesse link Spotify.")

    return [_track_from_spotify_search(search, requested_by) for search in searches]


def _spotify_track_searches(link: SpotifyLink) -> list[SpotifyTrackSearch]:
    if link.kind == "track":
        return [_spotify_track_search(link)]

    if link.kind == "playlist":
        return _spotify_playlist_track_searches(link.item_id)

    if link.kind == "album":
        return _spotify_album_track_searches(link.item_id)

    raise MusicError("Links de artista do Spotify ainda nao sao suportados. Usa uma musica, playlist ou album.")


def _spotify_track_search(link: SpotifyLink) -> SpotifyTrackSearch:
    if _spotify_credentials_available():
        try:
            payload = _spotify_api_get(f"tracks/{link.item_id}", _spotify_access_token())
            return _spotify_track_search_from_payload(payload)
        except MusicError:
            return _spotify_track_search_from_oembed(link.url)

    return _spotify_track_search_from_oembed(link.url)


def _spotify_playlist_track_searches(playlist_id: str) -> list[SpotifyTrackSearch]:
    token = _spotify_user_access_token()
    limit = _spotify_queue_limit()
    searches: list[SpotifyTrackSearch] = []
    offset = 0

    while len(searches) < limit:
        page_limit = min(50, limit - len(searches))
        payload = _spotify_api_get(
            f"playlists/{playlist_id}/items",
            token,
            params={
                "limit": str(page_limit),
                "offset": str(offset),
                "fields": "items(item(name,type,is_local,artists(name)),track(name,type,is_local,artists(name))),next,total",
                "additional_types": "track",
            },
        )
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            break

        searches.extend(_spotify_track_searches_from_wrapped_items(items, limit - len(searches)))
        if not payload.get("next"):
            break

        offset += page_limit

    return searches


def _spotify_album_track_searches(album_id: str) -> list[SpotifyTrackSearch]:
    token = _spotify_access_token()
    limit = _spotify_queue_limit()
    searches: list[SpotifyTrackSearch] = []
    offset = 0

    while len(searches) < limit:
        page_limit = min(50, limit - len(searches))
        payload = _spotify_api_get(
            f"albums/{album_id}/tracks",
            token,
            params={"limit": str(page_limit), "offset": str(offset)},
        )
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            break

        searches.extend(_spotify_track_searches_from_items(items, limit - len(searches)))
        if not payload.get("next"):
            break

        offset += page_limit

    return searches


def _spotify_track_searches_from_wrapped_items(
    items: list[object],
    limit: int,
) -> list[SpotifyTrackSearch]:
    tracks: list[SpotifyTrackSearch] = []
    for item in items:
        if len(tracks) >= limit:
            break
        if not isinstance(item, dict):
            continue
        track = item.get("item") or item.get("track")
        if not isinstance(track, dict):
            continue
        try:
            tracks.append(_spotify_track_search_from_payload(track))
        except MusicError:
            continue
    return tracks


def _spotify_track_searches_from_items(items: list[object], limit: int) -> list[SpotifyTrackSearch]:
    tracks: list[SpotifyTrackSearch] = []
    for item in items:
        if len(tracks) >= limit:
            break
        if not isinstance(item, dict):
            continue
        try:
            tracks.append(_spotify_track_search_from_payload(item))
        except MusicError:
            continue
    return tracks


def _spotify_track_search_from_payload(payload: dict[str, object]) -> SpotifyTrackSearch:
    if payload.get("is_local") is True:
        raise MusicError("musica local do Spotify ignorada.")

    track_type = payload.get("type")
    if isinstance(track_type, str) and track_type != "track":
        raise MusicError("item Spotify nao e uma musica.")

    title = str(payload.get("name") or "").strip()
    if not title:
        raise MusicError("musica Spotify sem titulo.")

    artists = []
    raw_artists = payload.get("artists")
    if isinstance(raw_artists, list):
        for artist in raw_artists:
            if isinstance(artist, dict):
                name = str(artist.get("name") or "").strip()
                if name:
                    artists.append(name)

    return SpotifyTrackSearch(title=title, artists=tuple(artists))


def _spotify_track_search_from_oembed(url: str) -> SpotifyTrackSearch:
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

    artists = (author,) if author else ()
    return SpotifyTrackSearch(title=title, artists=artists)


def _track_from_spotify_search(search: SpotifyTrackSearch, requested_by: str) -> Track:
    artists = ", ".join(search.artists)
    title = f"{search.title} - {artists}" if artists else search.title
    search_terms = " ".join(part for part in (search.title, artists, "official audio") if part)
    return Track(title=title, webpage_url=f"ytsearch1:{search_terms}", requested_by=requested_by)


_SPOTIFY_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def _spotify_access_token() -> str:
    if _spotify_refresh_token():
        return _spotify_user_access_token()
    return _spotify_client_credentials_access_token()


def _spotify_user_access_token() -> str:
    refresh_token = _spotify_refresh_token()
    if not refresh_token:
        raise MusicError(
            "Para playlists do Spotify, define `SPOTIFY_REFRESH_TOKEN`. "
            "A playlist tambem tem de ser tua ou uma playlist onde es colaborador."
        )

    return _spotify_refresh_access_token(refresh_token)


def _spotify_client_credentials_access_token() -> str:
    cache_key = "client_credentials"
    cached = _read_spotify_token_cache(cache_key)
    if cached:
        return cached

    credentials = _spotify_credentials()
    if credentials is None:
        raise MusicError(
            "Para playlists/albuns do Spotify, define `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`."
        )

    client_id, client_secret = credentials
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise MusicError("Nao consegui autenticar na API do Spotify.") from exc

    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise MusicError("A API do Spotify nao devolveu access token.")

    expires_in = int(payload.get("expires_in") or 3600)
    _write_spotify_token_cache(cache_key, token, expires_in)
    return token


def _spotify_refresh_access_token(refresh_token: str) -> str:
    cache_key = "refresh_token"
    cached = _read_spotify_token_cache(cache_key)
    if cached:
        return cached

    credentials = _spotify_credentials()
    if credentials is None:
        raise MusicError(
            "Para usar `SPOTIFY_REFRESH_TOKEN`, tambem tens de definir "
            "`SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`."
        )

    client_id, client_secret = credentials
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _spotify_http_error_detail(exc)
        raise MusicError(f"Nao consegui renovar o token do Spotify. {detail}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MusicError("Nao consegui renovar o token do Spotify.") from exc

    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise MusicError("A API do Spotify nao devolveu access token ao renovar o token.")

    expires_in = int(payload.get("expires_in") or 3600)
    _write_spotify_token_cache(cache_key, token, expires_in)
    return token


def _read_spotify_token_cache(cache_key: str) -> str | None:
    now = time.time()
    cached = _SPOTIFY_TOKEN_CACHE.get(cache_key)
    if cached is None:
        return None

    token, expires_at = cached
    if expires_at > now + 60:
        return token
    return None


def _write_spotify_token_cache(cache_key: str, token: str, expires_in: int) -> None:
    _SPOTIFY_TOKEN_CACHE[cache_key] = (token, time.time() + expires_in)


def _spotify_credentials_available() -> bool:
    return _spotify_credentials() is not None


def _spotify_credentials() -> tuple[str, str] | None:
    client_id = os.getenv(SPOTIFY_CLIENT_ID_ENV, "").strip()
    client_secret = os.getenv(SPOTIFY_CLIENT_SECRET_ENV, "").strip()
    if client_id and client_secret:
        return client_id, client_secret
    return None


def _spotify_refresh_token() -> str:
    refresh_token = os.getenv(SPOTIFY_REFRESH_TOKEN_ENV, "").strip()
    if not refresh_token:
        return ""

    if refresh_token.startswith(("http://", "https://")) or "code=" in refresh_token:
        raise MusicError(
            "`SPOTIFY_REFRESH_TOKEN` nao deve ser o URL de callback nem o valor de `code=`. "
            "Corre `python tools/spotify_refresh_token.py`, cola o URL final no terminal, "
            "e copia para o `.env` apenas o valor que o script imprimir depois de `SPOTIFY_REFRESH_TOKEN=`."
        )

    return refresh_token


def _spotify_api_get(
    path: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
) -> dict[str, object]:
    url = f"https://api.spotify.com/v1/{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_detail = _spotify_http_error_detail(exc)
        if exc.code == 401:
            raise MusicError(f"Credenciais Spotify invalidas ou expiradas. {error_detail}") from exc
        if exc.code == 404:
            raise MusicError(f"Nao encontrei esse link Spotify. {error_detail}") from exc
        raise MusicError(f"A API do Spotify recusou o pedido. {error_detail}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MusicError("Nao consegui ler dados da API do Spotify.") from exc

    if not isinstance(payload, dict):
        raise MusicError("Resposta invalida da API do Spotify.")
    return payload


def _spotify_http_error_detail(exc: urllib.error.HTTPError) -> str:
    detail = f"HTTP {exc.code}"
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        return detail

    if not body:
        return detail

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f"{detail}: {body[:160]}"

    message = _spotify_error_message(payload)
    if message:
        return f"{detail}: {message}"
    return detail


def _spotify_error_message(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message.strip()
    if isinstance(error, str):
        description = payload.get("error_description")
        if isinstance(description, str) and description.strip():
            return f"{error}: {description.strip()}"
        return error.strip()
    return ""


def _spotify_queue_limit() -> int:
    raw = os.getenv(SPOTIFY_QUEUE_LIMIT_ENV, str(DEFAULT_SPOTIFY_QUEUE_LIMIT)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SPOTIFY_QUEUE_LIMIT

    return max(1, min(value, MAX_SPOTIFY_QUEUE_LIMIT))


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
