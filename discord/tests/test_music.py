import unittest
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bot.music import (
    GuildMusicState,
    MusicError,
    SpotifyTrackSearch,
    Track,
    _ffmpeg_executable,
    _spotify_api_get,
    _spotify_access_token,
    _spotify_refresh_token,
    _parse_spotify_link,
    _prepare_query,
    _reset_music_state,
    _spotify_playlist_track_searches,
    resolve_tracks,
)


class MusicQueryTest(unittest.TestCase):
    def test_prepare_query_accepts_discord_suppressed_url(self):
        query = _prepare_query("<https://www.youtube.com/watch?v=dQw4w9WgXcQ>")

        self.assertEqual(query, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_prepare_query_extracts_url_from_text(self):
        query = _prepare_query("toca isto https://youtu.be/dQw4w9WgXcQ?si=abc")

        self.assertEqual(query, "https://youtu.be/dQw4w9WgXcQ?si=abc")

    def test_prepare_query_removes_trailing_url_punctuation(self):
        query = _prepare_query("https://www.youtube.com/watch?v=dQw4w9WgXcQ.")

        self.assertEqual(query, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_prepare_query_keeps_text_search(self):
        query = _prepare_query("never gonna give you up")

        self.assertEqual(query, "ytsearch1:never gonna give you up")

    def test_parse_spotify_link_accepts_localized_track_url(self):
        link = _parse_spotify_link("https://open.spotify.com/intl-pt/track/abc123?si=test")

        self.assertIsNotNone(link)
        self.assertEqual(link.kind, "track")
        self.assertEqual(link.item_id, "abc123")

    def test_spotify_playlist_tracks_are_read_from_api(self):
        payload = {
            "items": [
                {"item": {"name": "Song A", "type": "track", "artists": [{"name": "Artist A"}]}},
                {"item": {"name": "Song B", "type": "track", "artists": [{"name": "Artist B"}]}},
                {"item": {"name": "Local", "type": "track", "is_local": True, "artists": []}},
            ],
            "next": None,
        }

        with (
            patch("bot.music._spotify_user_access_token", return_value="token"),
            patch("bot.music._spotify_api_get", return_value=payload) as api_get,
            patch.dict("os.environ", {"SPOTIFY_QUEUE_LIMIT": "2"}),
        ):
            tracks = _spotify_playlist_track_searches("playlist123")

        self.assertEqual(tracks, [SpotifyTrackSearch("Song A", ("Artist A",)), SpotifyTrackSearch("Song B", ("Artist B",))])
        self.assertEqual(api_get.call_args.args[:2], ("playlists/playlist123/items", "token"))
        self.assertEqual(api_get.call_args.kwargs["params"]["limit"], "2")
        self.assertEqual(api_get.call_args.kwargs["params"]["offset"], "0")
        self.assertEqual(api_get.call_args.kwargs["params"]["additional_types"], "track")
        self.assertIn("item(name", api_get.call_args.kwargs["params"]["fields"])

    def test_spotify_api_get_encodes_query_params(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return b'{"items": []}'

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            return Response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _spotify_api_get(
                "playlists/playlist123/items",
                "token",
                params={
                    "limit": "2",
                    "offset": "0",
                    "fields": "items(track(name,type,is_local,artists(name))),next",
                },
            )

        self.assertIn("limit=2", captured["url"])
        self.assertIn("offset=0", captured["url"])
        self.assertIn("fields=items%28track", captured["url"])

    def test_spotify_access_token_prefers_refresh_token(self):
        with (
            patch("bot.music._spotify_user_access_token", return_value="user-token") as user_token,
            patch.dict("os.environ", {"SPOTIFY_REFRESH_TOKEN": "refresh"}),
        ):
            token = _spotify_access_token()

        self.assertEqual(token, "user-token")
        user_token.assert_called_once()

    def test_spotify_refresh_token_rejects_callback_url(self):
        with patch.dict("os.environ", {"SPOTIFY_REFRESH_TOKEN": "http://127.0.0.1:8888/callback?code=abc&state=def"}):
            with self.assertRaises(MusicError):
                _spotify_refresh_token()

    def test_ffmpeg_executable_accepts_directory_env(self):
        with TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "ffmpeg.exe"
            executable.write_text("", encoding="utf-8")

            with patch.dict("os.environ", {"FFMPEG_EXECUTABLE": temp_dir}):
                self.assertEqual(Path(_ffmpeg_executable()), executable)

    def test_ffmpeg_executable_accepts_quoted_file_env(self):
        with TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "ffmpeg.exe"
            executable.write_text("", encoding="utf-8")

            with patch.dict("os.environ", {"FFMPEG_EXECUTABLE": f'"{executable}"'}):
                self.assertEqual(Path(_ffmpeg_executable()), executable)

    def test_reset_music_state_clears_playback_and_queue(self):
        text_channel = object()
        state = GuildMusicState(
            queue=deque([Track("Queued", "https://example.com", "Tester")]),
            history=[Track("Old", "https://example.com/old", "Tester")],
            current=Track("Current", "https://example.com/current", "Tester"),
            loop_current=True,
            override_next=Track("Override", "https://example.com/override", "Tester"),
            ignore_loop_once=True,
            suppress_history_once=True,
            suppress_queue_end_once=True,
            text_channel=text_channel,
        )

        _reset_music_state(state, keep_text_channel=True)

        self.assertFalse(state.queue)
        self.assertFalse(state.history)
        self.assertIsNone(state.current)
        self.assertFalse(state.loop_current)
        self.assertIsNone(state.override_next)
        self.assertFalse(state.ignore_loop_once)
        self.assertFalse(state.suppress_history_once)
        self.assertFalse(state.suppress_queue_end_once)
        self.assertIs(state.text_channel, text_channel)


class MusicResolveTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_tracks_uses_spotify_resolver_for_localized_track_url(self):
        with patch("bot.music._spotify_track_searches", return_value=[SpotifyTrackSearch("Song", ("Artist",))]):
            tracks = await resolve_tracks("https://open.spotify.com/intl-pt/track/abc123?si=test", "Tester")

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].title, "Song - Artist")
        self.assertEqual(tracks[0].webpage_url, "ytsearch1:Song Artist official audio")
        self.assertEqual(tracks[0].requested_by, "Tester")


if __name__ == "__main__":
    unittest.main()
