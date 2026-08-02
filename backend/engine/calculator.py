"""Expected-value calculations based on sharp-market fair probabilities."""

from .math_utils import american_to_implied, de_vig_odds


def calculate_edge(
    sharp_home_odds: int,
    sharp_away_odds: int,
    rec_home_odds: int,
    stake: float = 100.0,
) -> float:
    """Return the home-moneyline expected value for a recommended-book wager."""
    if stake < 0.0:
        raise ValueError("Stake cannot be negative.")

    fair_home_probability, _ = de_vig_odds(sharp_home_odds, sharp_away_odds)
    fair_loss_probability = 1.0 - fair_home_probability
    recommended_implied_probability = american_to_implied(rec_home_odds)
    potential_profit = stake * ((1.0 / recommended_implied_probability) - 1.0)

    expected_value = (
        fair_home_probability * potential_profit
        - fair_loss_probability * stake
    )
    return round(expected_value, 2)
