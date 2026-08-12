"""HTTP and WebSocket endpoints exposing positive expected-value bets."""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.selectable import ScalarSelect

from db.database import get_db
from db.models import Game, OddsSnapshot, Sportsbook
from engine.calculator import calculate_edge


logger = logging.getLogger(__name__)

router = APIRouter(tags=["ev-bets"])
EV_STREAM_INTERVAL_SECONDS = 10.0


class EVBet(BaseModel):
    """A positive expected-value moneyline opportunity."""

    game_id: int
    home_team: str
    away_team: str
    recommended_bet: str
    recreational_odds: int
    expected_value: float


class ConnectionManager:
    """Track WebSocket clients and broadcast one shared EV-bet stream."""

    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()
        self._broadcast_task: asyncio.Task[None] | None = None

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a client, starting the polling loop if needed."""
        await websocket.accept()
        self.active_connections.add(websocket)
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self._broadcast_ev_bets())

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a client and stop polling when no clients remain."""
        self.active_connections.discard(websocket)
        if self.active_connections or self._broadcast_task is None:
            return

        broadcast_task = self._broadcast_task
        self._broadcast_task = None
        broadcast_task.cancel()

    async def broadcast(self, payload: list[dict[str, object]]) -> None:
        """Send a JSON payload to every connected client."""
        disconnected_clients: list[WebSocket] = []
        for connection in tuple(self.active_connections):
            try:
                await connection.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                disconnected_clients.append(connection)

        for connection in disconnected_clients:
            self.disconnect(connection)

    async def _broadcast_ev_bets(self) -> None:
        """Fetch and broadcast current +EV bets every configured interval."""
        try:
            while self.active_connections:
                ev_bets = _load_current_ev_bets()
                await self.broadcast(
                    [ev_bet.model_dump(mode="json") for ev_bet in ev_bets]
                )
                await asyncio.sleep(EV_STREAM_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        finally:
            if not self.active_connections:
                self._broadcast_task = None


manager = ConnectionManager()


@router.get("/api/v1/ev-bets", response_model=list[EVBet])
def get_positive_ev_bets(db: Session = Depends(get_db)) -> list[EVBet]:
    """Return current home or away moneylines with a strictly positive EV."""
    return _query_positive_ev_bets(db)


@router.websocket("/api/v1/ev-stream")
async def stream_positive_ev_bets(websocket: WebSocket) -> None:
    """Stream the latest +EV bets to each connected dashboard client."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def _load_current_ev_bets() -> list[EVBet]:
    """Use the standard get_db dependency to create and close one poll session."""
    db_dependency = get_db()
    db = next(db_dependency)
    try:
        return _query_positive_ev_bets(db)
    except Exception:
        logger.exception("Unable to load +EV bets for WebSocket clients.")
        return []
    finally:
        db_dependency.close()


def _query_positive_ev_bets(db: Session) -> list[EVBet]:
    """Query latest Pinnacle/FanDuel odds and calculate positive home/away edges."""
    pinnacle_snapshot = aliased(OddsSnapshot)
    fanduel_snapshot = aliased(OddsSnapshot)

    latest_pinnacle_snapshot_id = _latest_snapshot_id_for("Pinnacle")
    latest_fanduel_snapshot_id = _latest_snapshot_id_for("FanDuel")
    statement = (
        select(Game, pinnacle_snapshot, fanduel_snapshot)
        .select_from(Game)
        .join(pinnacle_snapshot, pinnacle_snapshot.id == latest_pinnacle_snapshot_id)
        .join(fanduel_snapshot, fanduel_snapshot.id == latest_fanduel_snapshot_id)
        .where(Game.start_time >= datetime.now(timezone.utc))
    )

    ev_bets: list[EVBet] = []
    for game, sharp_odds, recreational_odds in db.execute(statement).all():
        _append_positive_edge(
            ev_bets=ev_bets,
            game=game,
            sharp_home_odds=sharp_odds.home_odds,
            sharp_away_odds=sharp_odds.away_odds,
            recreational_home_odds=recreational_odds.home_odds,
            recommended_bet=game.home_team,
        )
        _append_positive_edge(
            ev_bets=ev_bets,
            game=game,
            sharp_home_odds=sharp_odds.away_odds,
            sharp_away_odds=sharp_odds.home_odds,
            recreational_home_odds=recreational_odds.away_odds,
            recommended_bet=game.away_team,
        )

    return ev_bets


def _latest_snapshot_id_for(sportsbook_name: str) -> ScalarSelect[int]:
    """Return a correlated subquery for a game's newest sportsbook snapshot."""
    return (
        select(OddsSnapshot.id)
        .join(Sportsbook)
        .where(
            OddsSnapshot.game_id == Game.id,
            Sportsbook.name == sportsbook_name,
        )
        .order_by(OddsSnapshot.timestamp.desc(), OddsSnapshot.id.desc())
        .limit(1)
        .correlate(Game)
        .scalar_subquery()
    )


def _append_positive_edge(
    ev_bets: list[EVBet],
    game: Game,
    sharp_home_odds: int,
    sharp_away_odds: int,
    recreational_home_odds: int,
    recommended_bet: str,
) -> None:
    """Append a wager only when valid inputs produce a strictly positive EV."""
    try:
        expected_value = calculate_edge(
            sharp_home_odds=sharp_home_odds,
            sharp_away_odds=sharp_away_odds,
            rec_home_odds=recreational_home_odds,
        )
    except ValueError:
        return

    if expected_value <= 0.0:
        return

    ev_bets.append(
        EVBet(
            game_id=game.id,
            home_team=game.home_team,
            away_team=game.away_team,
            recommended_bet=recommended_bet,
            recreational_odds=recreational_home_odds,
            expected_value=expected_value,
        )
    )
