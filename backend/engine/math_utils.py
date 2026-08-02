"""Odds conversion and proportional de-vigging functions."""


def american_to_implied(odds: int) -> float:
    """Convert non-zero American odds to an implied probability from 0.0 to 1.0."""
    if odds == 0:
        raise ValueError("American odds cannot be zero.")

    if odds > 0:
        return 100.0 / (odds + 100.0)

    absolute_odds = abs(odds)
    return absolute_odds / (absolute_odds + 100.0)


def calculate_vig(home_odds: int, away_odds: int) -> float:
    """Return the two-sided market overround as a decimal proportion."""
    return american_to_implied(home_odds) + american_to_implied(away_odds) - 1.0


def de_vig_odds(home_odds: int, away_odds: int) -> tuple[float, float]:
    """Return proportional de-vigged home and away win probabilities."""
    home_implied = american_to_implied(home_odds)
    away_implied = american_to_implied(away_odds)
    total_implied = home_implied + away_implied

    return home_implied / total_implied, away_implied / total_implied
