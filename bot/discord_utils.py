from __future__ import annotations

from collections.abc import Awaitable, Callable


DISCORD_MESSAGE_LIMIT = 2000
SAFE_MESSAGE_LIMIT = 1900


async def send_text(send: Callable[[str], Awaitable[object]], text: str) -> None:
    if len(text) <= DISCORD_MESSAGE_LIMIT:
        await send(text)
        return

    for chunk in _split_text(text):
        await send(chunk)


def _split_text(text: str) -> list[str]:
    chunks: list[str] = []
    remaining = text

    while len(remaining) > SAFE_MESSAGE_LIMIT:
        split_at = remaining.rfind("\n", 0, SAFE_MESSAGE_LIMIT)
        if split_at <= 0:
            split_at = SAFE_MESSAGE_LIMIT

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks
