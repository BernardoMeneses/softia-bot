import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.server_settings import ServerSettings


class ServerSettingsTest(unittest.TestCase):
    def test_event_channel_id_is_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "server_settings.json"
            settings = ServerSettings(path)

            settings.set_event_channel_id(123, 456)

            reloaded = ServerSettings(path)
            self.assertEqual(reloaded.get_event_channel_id(123), 456)

    def test_event_channel_id_falls_back_to_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "server_settings.json"

            with patch.dict("os.environ", {"EVENT_CHANNEL_ID": "789"}):
                settings = ServerSettings(path)
                self.assertEqual(settings.get_event_channel_id(123), 789)

    def test_events_enabled_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "server_settings.json"
            settings = ServerSettings(path)

            settings.set_events_enabled(123, False)

            reloaded = ServerSettings(path)
            self.assertFalse(reloaded.events_enabled(123))

    def test_spam_guard_enabled_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "server_settings.json"
            settings = ServerSettings(path)

            settings.set_spam_guard_enabled(123, False)

            reloaded = ServerSettings(path)
            self.assertFalse(reloaded.spam_guard_enabled(123))

    def test_default_path_can_be_configured_with_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state" / "server_settings.json"

            with patch.dict("os.environ", {"SERVER_SETTINGS_PATH": str(path)}):
                settings = ServerSettings()
                settings.set_event_channel_id(123, 456)

                self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
