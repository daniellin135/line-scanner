"""Asynchronous SharpAPI client for sharp and retail moneyline odds."""

import asyncio
import logging
import os
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, TypedDict

import aiohttp


logger = logging.getLogger(__name__)

SHARP_API_ODDS_URL = "https://api.sharpapi.io/api/v1/odds"
LEAGUES: tuple[str, str] = ("NBA", "MLB")
TARGET_BOOKS: frozenset[str] = frozenset({"pinnacle", "fanduel"})


class CleanOdds(TypedDict):
    """A moneyline price available from both target sportsbooks."""

    game_id: str
    sport: str
    team: str
    pinnacle_odds: float
    fanduel_odds: float


class SharpAPIRateLimitError(Exception):
    """Raised when SharpAPI rejects a request because of its rate limit."""


async def fetch_upcoming_moneyline_odds(
    timeout_seconds: float = 10.0,
) -> list[CleanOdds]:
    """Fetch upcoming NBA and MLB moneylines from SharpAPI.

    The ``SHARP_API_KEY`` environment variable is sent as a Bearer token. Only
    teams quoted by both Pinnacle and FanDuel are included in the result.
    """
    api_key = os.getenv("SHARP_API_KEY")
    if not api_key:
        logger.warning("SHARP_API_KEY is not configured; skipping odds fetch.")
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            requests = [_fetch_league_odds(session, league) for league in LEAGUES]
            responses = await asyncio.gather(*requests, return_exceptions=True)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.exception("Unable to request odds from SharpAPI.")
        return []

    cleaned_odds: list[CleanOdds] = []
    for league, response in zip(LEAGUES, responses):
        if isinstance(response, SharpAPIRateLimitError):
            return []
        if isinstance(response, BaseException):
            logger.warning("SharpAPI request for %s failed: %s", league, response)
            continue
        cleaned_odds.extend(_parse_odds_rows(league, response))

    return cleaned_odds


async def _fetch_league_odds(
    session: aiohttp.ClientSession,
    league: str,
) -> list[dict[str, Any]]:
    """Request one league's moneyline odds and validate SharpAPI's response."""
    params = {"league": league, "market": "moneyline"}

    try:
        async with session.get(SHARP_API_ODDS_URL, params=params) as response:
            if response.status == HTTPStatus.TOO_MANY_REQUESTS:
                logger.warning("SharpAPI rate limit reached while fetching %s odds.", league)
                raise SharpAPIRateLimitError(league)
            response.raise_for_status()
            payload: Any = await response.json()
    except (
        aiohttp.ClientError,
        aiohttp.ContentTypeError,
        asyncio.TimeoutError,
        ValueError,
    ):
        logger.exception("Invalid or unavailable SharpAPI response for %s.", league)
        return []

    if not isinstance(payload, Mapping):
        logger.warning("SharpAPI returned a non-object payload for %s.", league)
        return []

    rows = payload.get("data")
    if not isinstance(rows, list):
        logger.warning("SharpAPI response for %s did not contain a data list.", league)
        return []

    return [row for row in rows if isinstance(row, dict)]


def _parse_odds_rows(league: str, rows: list[dict[str, Any]]) -> list[CleanOdds]:
    """Combine SharpAPI Pinnacle and FanDuel moneylines by game and team."""
    prices: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        if not _is_moneyline(row):
            continue

        sportsbook = row.get("sportsbook")
        game_id = _get_game_id(row)
        team = row.get("selection")
        odds = row.get("odds_american")
        if (
            not isinstance(sportsbook, str)
            or sportsbook.lower() not in TARGET_BOOKS
            or game_id is None
            or not isinstance(team, str)
            or not isinstance(odds, (int, float))
        ):
            continue

        prices.setdefault((game_id, team), {})[sportsbook.lower()] = float(odds)

    cleaned_odds: list[CleanOdds] = []
    for (game_id, team), book_prices in prices.items():
        pinnacle_odds = book_prices.get("pinnacle")
        fanduel_odds = book_prices.get("fanduel")
        if pinnacle_odds is None or fanduel_odds is None:
            continue
        cleaned_odds.append(
            {
                "game_id": game_id,
                "sport": league,
                "team": team,
                "pinnacle_odds": pinnacle_odds,
                "fanduel_odds": fanduel_odds,
            }
        )

    return cleaned_odds


def _is_moneyline(row: Mapping[str, Any]) -> bool:
    """Determine whether a SharpAPI odds row represents a moneyline market."""
    market = row.get("market_type", row.get("market"))
    return isinstance(market, str) and market.lower() in {"moneyline", "h2h"}


def _get_game_id(row: Mapping[str, Any]) -> str | None:
    """Read a stable event identifier from supported SharpAPI event-id fields."""
    for key in ("game_id", "event_id", "id"):
        value = row.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    return None
