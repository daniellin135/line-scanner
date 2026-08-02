"""Database write operations for normalized sportsbook odds."""

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Game, OddsSnapshot, Sportsbook
from workers.odds_client import CleanOdds


logger = logging.getLogger(__name__)

BookOddsField = Literal["pinnacle_odds", "fanduel_odds"]
BOOK_FIELDS: tuple[tuple[str, BookOddsField], tuple[str, BookOddsField]] = (
    ("Pinnacle", "pinnacle_odds"),
    ("FanDuel", "fanduel_odds"),
)


def save_odds_snapshot(
    db: Session,
    cleaned_odds: Sequence[CleanOdds],
) -> list[OddsSnapshot]:
    """Persist one Pinnacle and one FanDuel snapshot for each complete game.

    The cleaned odds payload contains one row per team. Rows are grouped by the
    provider game ID so both sides of each moneyline market form one snapshot.
    """
    grouped_odds = _group_odds_by_game(cleaned_odds)
    created_snapshots: list[OddsSnapshot] = []

    try:
        sportsbooks = {
            name: _get_or_create_sportsbook(db, name) for name, _ in BOOK_FIELDS
        }

        for game_id, rows in grouped_odds.items():
            game = _get_or_create_game(db, game_id, rows)
            if game is None:
                continue

            odds_by_team = {row["team"]: row for row in rows}
            home_odds_row = odds_by_team[game.home_team]
            away_odds_row = odds_by_team[game.away_team]

            for sportsbook_name, odds_field in BOOK_FIELDS:
                snapshot = OddsSnapshot(
                    game=game,
                    sportsbook=sportsbooks[sportsbook_name],
                    home_odds=int(home_odds_row[odds_field]),
                    away_odds=int(away_odds_row[odds_field]),
                )
                db.add(snapshot)
                created_snapshots.append(snapshot)

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to save odds snapshots; transaction rolled back.")
        raise

    return created_snapshots


def _group_odds_by_game(
    cleaned_odds: Sequence[CleanOdds],
) -> dict[str, list[CleanOdds]]:
    """Group valid team odds rows by their upstream event identifier."""
    grouped_odds: defaultdict[str, list[CleanOdds]] = defaultdict(list)
    for row in cleaned_odds:
        grouped_odds[row["game_id"]].append(row)
    return dict(grouped_odds)


def _get_or_create_sportsbook(db: Session, name: str) -> Sportsbook:
    """Find a sportsbook by name or add it to the current transaction."""
    sportsbook = db.scalar(select(Sportsbook).where(Sportsbook.name == name))
    if sportsbook is not None:
        return sportsbook

    sportsbook = Sportsbook(name=name)
    db.add(sportsbook)
    db.flush()
    return sportsbook


def _get_or_create_game(
    db: Session,
    external_game_id: str,
    rows: Sequence[CleanOdds],
) -> Game | None:
    """Find a game by its internal ID or matchup, creating a complete matchup."""
    teams = sorted({row["team"] for row in rows})
    if len(teams) != 2:
        logger.warning(
            "Skipping game %s because it has %d teams instead of two.",
            external_game_id,
            len(teams),
        )
        return None

    sport = rows[0]["sport"]
    game = _find_game(db, external_game_id, sport, teams[0], teams[1])
    if game is not None:
        return game

    game = Game(
        sport=sport,
        home_team=teams[0],
        away_team=teams[1],
        start_time=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()
    return game


def _find_game(
    db: Session,
    external_game_id: str,
    sport: str,
    first_team: str,
    second_team: str,
) -> Game | None:
    """Find a game by numeric ID when possible, otherwise by either matchup order."""
    if external_game_id.isdigit():
        game = db.get(Game, int(external_game_id))
        if game is not None:
            return game

    matchup_filter = or_(
        (Game.home_team == first_team) & (Game.away_team == second_team),
        (Game.home_team == second_team) & (Game.away_team == first_team),
    )
    return db.scalar(select(Game).where(Game.sport == sport, matchup_filter))
