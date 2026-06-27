from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


COIN = "🪙"
DEFAULT_BALANCE = 100
DAILY_REWARD = 100
DAILY_COOLDOWN = timedelta(hours=24)
DEFAULT_GAME_STATE_PATH = Path("data/game_state.json")
GAME_STATE_PATH_ENV = "GAME_STATE_PATH"


class GameStoreError(ValueError):
    """Raised when a wallet or shop operation cannot be completed."""


@dataclass(frozen=True)
class ShopItem:
    item_id: str
    name: str
    price: int
    description: str


SHOP_ITEMS = (
    ShopItem("vip", "VIP Badge", 500, "A shiny status item for your inventory."),
    ShopItem("luck", "Lucky Charm", 350, "A collectible charm for casino nights."),
    ShopItem("crown", "Server Crown", 1000, "Flex item for the richest players."),
    ShopItem("ticket", "Event Ticket", 50, "A cheap collectible for event winners."),
    ShopItem("boost", "XP Boost Token", 250, "A cosmetic boost token."),
)


class GameStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_game_state_path()
        self._state = self._load()

    def balance(self, guild_id: int, user_id: int) -> int:
        return int(self._user(guild_id, user_id).get("coins", DEFAULT_BALANCE))

    def inventory(self, guild_id: int, user_id: int) -> dict[str, int]:
        inventory = self._user(guild_id, user_id).setdefault("inventory", {})
        return {str(item_id): int(quantity) for item_id, quantity in inventory.items() if int(quantity) > 0}

    def add_coins(self, guild_id: int, user_id: int, amount: int) -> int:
        user = self._user(guild_id, user_id)
        user["coins"] = self.balance(guild_id, user_id) + amount
        self._save()
        return int(user["coins"])

    def spend_coins(self, guild_id: int, user_id: int, amount: int) -> int:
        if amount <= 0:
            raise GameStoreError("Amount must be positive.")

        balance = self.balance(guild_id, user_id)
        if balance < amount:
            raise GameStoreError(f"Not enough coins. You have {format_coins(balance)}.")

        user = self._user(guild_id, user_id)
        user["coins"] = balance - amount
        self._save()
        return int(user["coins"])

    def claim_daily(self, guild_id: int, user_id: int) -> tuple[int, timedelta | None]:
        user = self._user(guild_id, user_id)
        now = datetime.now(UTC)
        last_claim_raw = user.get("last_daily")

        if isinstance(last_claim_raw, str):
            last_claim = _parse_datetime(last_claim_raw)
            if last_claim is not None:
                remaining = DAILY_COOLDOWN - (now - last_claim)
                if remaining.total_seconds() > 0:
                    return self.balance(guild_id, user_id), remaining

        user["last_daily"] = now.isoformat()
        user["coins"] = self.balance(guild_id, user_id) + DAILY_REWARD
        self._save()
        return int(user["coins"]), None

    def buy_item(self, guild_id: int, user_id: int, item_id: str, quantity: int = 1) -> tuple[ShopItem, int]:
        if quantity <= 0:
            raise GameStoreError("Quantity must be positive.")

        item = get_shop_item(item_id)
        if item is None:
            raise GameStoreError("That item does not exist. Use `-shop`.")

        total = item.price * quantity
        self.spend_coins(guild_id, user_id, total)

        user = self._user(guild_id, user_id)
        inventory = user.setdefault("inventory", {})
        inventory[item.item_id] = int(inventory.get(item.item_id, 0)) + quantity
        self._save()
        return item, self.balance(guild_id, user_id)

    def leaderboard(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        guild = self._guild(guild_id)
        users = guild.get("users", {})
        entries = [(int(user_id), int(data.get("coins", DEFAULT_BALANCE))) for user_id, data in users.items()]
        return sorted(entries, key=lambda entry: entry[1], reverse=True)[:limit]

    def _user(self, guild_id: int, user_id: int) -> dict[str, Any]:
        users = self._guild(guild_id).setdefault("users", {})
        return users.setdefault(str(user_id), {"coins": DEFAULT_BALANCE, "inventory": {}})

    def _guild(self, guild_id: int) -> dict[str, Any]:
        guilds = self._state.setdefault("guilds", {})
        return guilds.setdefault(str(guild_id), {"users": {}})

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"guilds": {}}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"guilds": {}}

        return data if isinstance(data, dict) else {"guilds": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")


def get_shop_item(item_id: str) -> ShopItem | None:
    normalized = item_id.strip().lower()
    for item in SHOP_ITEMS:
        if item.item_id == normalized:
            return item
    return None


def format_coins(amount: int) -> str:
    return f"{COIN} {amount}"


def format_duration(delta: timedelta) -> str:
    seconds = max(int(delta.total_seconds()), 0)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def default_game_state_path() -> Path:
    configured = os.getenv(GAME_STATE_PATH_ENV, "").strip()
    if configured:
        return Path(configured)
    return DEFAULT_GAME_STATE_PATH


def _parse_datetime(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
