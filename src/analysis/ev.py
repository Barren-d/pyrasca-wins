from __future__ import annotations

DISCOUNT_RATE = 0.03


def baseline_ev(prize_tiers: list[dict], total_scenarios: int, price: float) -> tuple[float, float]:
    """Return (expected_return, expected_return_per_euro) from raw prize tiers.

    EV_base = Σᵢ (Wᵢ / T) × prizeᵢ − c
    """
    gross = sum(
        (tier["occurrences"] / total_scenarios) * tier["prize_amount"]
        for tier in prize_tiers
    )
    ev = gross - price
    return ev, ev / price


def annuity_pv(pmt: float, n: int, r: float = DISCOUNT_RATE) -> float:
    """Present value of an ordinary annuity: PMT × (1 − (1+r)^−n) / r."""
    return pmt * (1 - (1 + r) ** -n) / r
