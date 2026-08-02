"""SQLAlchemy models for games, sportsbooks, and odds history."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Game(Base):
    """A scheduled sporting event whose market prices are collected."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    home_team: Mapped[str] = mapped_column(String(100), nullable=False)
    away_team: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="OddsSnapshot.timestamp",
    )


class Sportsbook(Base):
    """A sportsbook supplying market prices."""

    __tablename__ = "sportsbooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship(
        back_populates="sportsbook",
        cascade="all, delete-orphan",
    )


class OddsSnapshot(Base):
    """One sportsbook's American-moneyline prices at a point in time."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    sportsbook_id: Mapped[int] = mapped_column(
        ForeignKey("sportsbooks.id"), nullable=False
    )
    home_odds: Mapped[int] = mapped_column(Integer, nullable=False)
    away_odds: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    game: Mapped[Game] = relationship(back_populates="odds_snapshots")
    sportsbook: Mapped[Sportsbook] = relationship(back_populates="odds_snapshots")
