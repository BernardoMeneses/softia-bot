import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.game_store import DEFAULT_BALANCE, GameStore, GameStoreError, format_coins


class GameStoreTest(unittest.TestCase):
    def test_default_balance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GameStore(Path(temp_dir) / "game_state.json")

            self.assertEqual(store.balance(1, 2), DEFAULT_BALANCE)

    def test_add_and_spend_coins_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "game_state.json"
            store = GameStore(path)

            store.add_coins(1, 2, 50)
            store.spend_coins(1, 2, 30)

            reloaded = GameStore(path)
            self.assertEqual(reloaded.balance(1, 2), DEFAULT_BALANCE + 20)

    def test_spend_rejects_insufficient_balance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GameStore(Path(temp_dir) / "game_state.json")

            with self.assertRaises(GameStoreError):
                store.spend_coins(1, 2, DEFAULT_BALANCE + 1)

    def test_buy_item_adds_inventory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GameStore(Path(temp_dir) / "game_state.json")

            item, _ = store.buy_item(1, 2, "ticket", 2)

            self.assertEqual(item.item_id, "ticket")
            self.assertEqual(store.inventory(1, 2)["ticket"], 2)

    def test_default_path_can_be_configured_with_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state" / "game_state.json"

            with patch.dict("os.environ", {"GAME_STATE_PATH": str(path)}):
                store = GameStore()
                store.add_coins(1, 2, 50)

                self.assertTrue(path.exists())

    def test_format_coins(self):
        self.assertEqual(format_coins(10), "🪙 10")


if __name__ == "__main__":
    unittest.main()
