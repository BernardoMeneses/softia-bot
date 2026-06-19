from __future__ import annotations

import asyncio
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup
from discord.ext import commands

from .discord_utils import send_text
from .messages import SEARCH_INFO_MESSAGE


class SearchError(RuntimeError):
    """Raised when a web search cannot be completed."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}

BLOCKED_DOMAINS = (
    "accounts.google.",
    "google.",
    "policies.google.",
    "support.google.",
    "webcache.googleusercontent.",
    "bing.com/search",
    "go.microsoft.com",
    "microsoft.com",
)


class SearchCog(commands.Cog):
    @commands.command(name="searchinfo")
    async def search_info(self, ctx: commands.Context) -> None:
        await ctx.send(SEARCH_INFO_MESSAGE)

    @commands.command(name="grepg")
    async def google(self, ctx: commands.Context, *, query: str = "") -> None:
        await self._send_results(ctx, "Google", query, search_google)

    @commands.command(name="grepb")
    async def bing(self, ctx: commands.Context, *, query: str = "") -> None:
        await self._send_results(ctx, "Bing", query, search_bing)

    async def _send_results(
        self,
        ctx: commands.Context,
        engine: str,
        query: str,
        search_func: Callable[[str, int], list[SearchResult]],
    ) -> None:
        query = query.strip()
        if not query:
            await ctx.send(f"Uso: `-grep{engine[0].lower()} <texto>`")
            return

        try:
            async with ctx.typing():
                results = await asyncio.to_thread(search_func, query, 5)
        except SearchError as exc:
            await ctx.send(str(exc))
            return

        if not results:
            await ctx.send(f"Nao encontrei resultados no {engine} para `{query}`.")
            return

        await send_text(ctx.send, format_results(engine, query, results))


def search_google(query: str, limit: int = 5) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query, "num": str(limit), "hl": "pt-PT"})
    html = _fetch_html(f"https://www.google.com/search?{params}")
    return parse_google_results(html, limit) or fallback_search(query, limit)


def search_bing(query: str, limit: int = 5) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query, "count": str(limit), "setlang": "pt-PT"})
    html = _fetch_html(f"https://www.bing.com/search?{params}")
    return parse_bing_results(html, limit) or fallback_search(query, limit)


def parse_google_results(html: str, limit: int = 5) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for anchor in soup.select("a"):
        href = anchor.get("href", "")
        url = _clean_google_href(href)
        title = anchor.get_text(" ", strip=True)

        if _is_valid_result(url) and title:
            _append_unique(results, SearchResult(_clean_title(title), url))

        if len(results) >= limit:
            break

    return results


def parse_bing_results(html: str, limit: int = 5) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for anchor in soup.select("li.b_algo h2 a"):
        href = anchor.get("href", "")
        title = anchor.get_text(" ", strip=True)

        if _is_valid_result(href) and title:
            _append_unique(results, SearchResult(_clean_title(title), href))

        if len(results) >= limit:
            break

    return results


def format_results(engine: str, query: str, results: list[SearchResult]) -> str:
    lines = [f"Resultados {engine} para `{query}`:"]
    for index, result in enumerate(results[:5], start=1):
        lines.append(f"{index}. [{result.title}]({result.url})")
    return "\n".join(lines)


def fallback_search(query: str, limit: int = 5) -> list[SearchResult]:
    try:
        from ddgs import DDGS

        raw_results = list(DDGS().text(query, max_results=limit))
    except Exception as exc:
        raise SearchError("Nao consegui obter resultados desta pesquisa agora.") from exc

    results: list[SearchResult] = []
    for item in raw_results:
        result = _result_from_ddgs_item(item)
        if result is not None:
            _append_unique(results, result)

        if len(results) >= limit:
            break

    return results


def _result_from_ddgs_item(item: dict[str, Any]) -> SearchResult | None:
    title = str(item.get("title") or "").strip()
    url = str(item.get("href") or item.get("url") or "").strip()

    if not title or not _is_valid_result(url):
        return None

    return SearchResult(_clean_title(title), url)


def _fetch_html(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SearchError("Nao consegui fazer essa pesquisa agora.") from exc

    return response.text


def _clean_google_href(href: str) -> str:
    if href.startswith("/url?"):
        query = urllib.parse.urlparse(href).query
        values = urllib.parse.parse_qs(query).get("q")
        return values[0] if values else ""

    return href


def _is_valid_result(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False

    lowered = url.lower()
    return not any(domain in lowered for domain in BLOCKED_DOMAINS)


def _append_unique(results: list[SearchResult], result: SearchResult) -> None:
    if any(existing.url == result.url for existing in results):
        return
    results.append(result)


def _clean_title(title: str) -> str:
    return " ".join(title.split())
