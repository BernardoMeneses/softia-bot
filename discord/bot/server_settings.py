from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_PATH = Path("data/server_settings.json")
SERVER_SETTINGS_PATH_ENV = "SERVER_SETTINGS_PATH"


class ServerSettings:
    def __init__(self, path: Path | None = None):
        self.path = path or default_settings_path()
        self._settings = self._load()

    def get_event_channel_id(self, guild_id: int) -> int | None:
        stored_channel = self._guild_settings(guild_id).get("event_channel_id")
        if isinstance(stored_channel, int):
            return stored_channel

        env_channel = os.getenv("EVENT_CHANNEL_ID", "").strip()
        if env_channel.isdigit():
            return int(env_channel)

        return None

    def set_event_channel_id(self, guild_id: int, channel_id: int) -> None:
        guild_settings = self._guild_settings(guild_id)
        guild_settings["event_channel_id"] = channel_id
        self._save()

    def events_enabled(self, guild_id: int) -> bool:
        enabled = self._guild_settings(guild_id).get("events_enabled")
        if isinstance(enabled, bool):
            return enabled

        env_enabled = os.getenv("EVENTS_ENABLED", "true").strip().lower()
        return env_enabled not in {"0", "false", "off", "no"}

    def set_events_enabled(self, guild_id: int, enabled: bool) -> None:
        guild_settings = self._guild_settings(guild_id)
        guild_settings["events_enabled"] = enabled
        self._save()

    def spam_guard_enabled(self, guild_id: int) -> bool:
        enabled = self._guild_settings(guild_id).get("spam_guard_enabled")
        if isinstance(enabled, bool):
            return enabled

        env_enabled = os.getenv("SPAM_GUARD_ENABLED", "true").strip().lower()
        return env_enabled not in {"0", "false", "off", "no"}

    def set_spam_guard_enabled(self, guild_id: int, enabled: bool) -> None:
        guild_settings = self._guild_settings(guild_id)
        guild_settings["spam_guard_enabled"] = enabled
        self._save()

    def _guild_settings(self, guild_id: int) -> dict[str, Any]:
        return self._settings.setdefault(str(guild_id), {})

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._settings, indent=2, sort_keys=True), encoding="utf-8")


def default_settings_path() -> Path:
    configured = os.getenv(SERVER_SETTINGS_PATH_ENV, "").strip()
    if configured:
        return Path(configured)
    return DEFAULT_SETTINGS_PATH
