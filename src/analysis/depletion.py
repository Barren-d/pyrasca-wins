from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from .retention import retention_days, is_calibrated

SCRAPE_INTERVAL_DAYS = 1 / 24  # hourly scrape → 1/24 day
K_MIN_RETENTION_FACTOR = 4     # tier must have retention ≥ 4 × scrape_interval
MIN_CLAIMS_FOR_RATE = 5
MIN_SCRAPING_DAYS = 14
AGE_PRIOR_MEDIAN_DAYS = 1825   # 5-year median game lifetime for fallback p̂
HIGH_SELL_THROUGH_THRESHOLD = 0.95  # above this T(1−p̂) is too small; fall back to base EV


def compute_adj_ev(
    snapshot_id: str,
    game_id: str,
    price: float,
    prize_tiers: list[dict[str, Any]],
    claimed_prizes: list[dict[str, Any]],
    game_start: date | None,
    scrape_start: date | None,
    today: date,
    empirical_retention: dict[float, float] | None,
    total_scenarios: int | None = None,
) -> dict[str, Any]:
    """Compute depletion-adjusted EV for one game × price snapshot.

    Returns a dict of fields to UPDATE on game_snapshots.
    """
    if not prize_tiers or not game_start:
        return _fallback(snapshot_id, prize_tiers, price, None, empirical_retention, total_scenarios)

    elapsed_days = (today - game_start).days
    scraping_days = (today - scrape_start).days if scrape_start else 0

    if elapsed_days <= 0:
        return _fallback(snapshot_id, prize_tiers, price, None, empirical_retention, total_scenarios)

    total_scenarios = total_scenarios or sum(t["occurrences"] for t in prize_tiers)
    if total_scenarios == 0:
        return _fallback(snapshot_id, prize_tiers, price, None, empirical_retention, total_scenarios)

    calibrated = is_calibrated(empirical_retention)

    # Build per-tier W_eff and claim count
    min_retention = K_MIN_RETENTION_FACTOR * SCRAPE_INTERVAL_DAYS

    claim_by_amount: dict[float, int] = {}
    for cp in claimed_prizes:
        amt = float(cp["prize_amount"])
        if cp.get("prize_tier_id"):  # only matched claims
            claim_by_amount[amt] = claim_by_amount.get(amt, 0) + 1

    observable: list[dict] = []
    for tier in prize_tiers:
        amt = float(tier["prize_amount"])
        ret = retention_days(amt, empirical_retention)
        w_eff = min(elapsed_days, scraping_days + ret)

        # condition (a): retention sufficient
        if ret < min_retention:
            continue
        # condition (b) + (c): only tiers with matched claims (prize_tier_id non-NULL)
        # represented here by the claim_by_amount lookup being populated from matched rows
        if amt not in claim_by_amount and claim_by_amount.get(amt, 0) == 0:
            # no observed claims is valid — it contributes 0 to numerator
            pass

        c_i = claim_by_amount.get(amt, 0)
        observable.append({
            "tier": tier,
            "amt": amt,
            "c_i": c_i,
            "w_eff": w_eff,
        })

    sum_c = sum(o["c_i"] for o in observable)
    sum_w_weff = sum(o["tier"]["occurrences"] * o["w_eff"] for o in observable)

    # Fallback: sparse observations
    if sum_c < MIN_CLAIMS_FOR_RATE or scraping_days < MIN_SCRAPING_DAYS or sum_w_weff == 0:
        p_hat = min(1.0, elapsed_days / AGE_PRIOR_MEDIAN_DAYS)
        return _fallback(snapshot_id, prize_tiers, price, p_hat, empirical_retention, total_scenarios)

    # MLE sell-through
    p_hat = min(1.0, (sum_c * elapsed_days) / sum_w_weff)
    se = math.sqrt(sum_c) * elapsed_days / sum_w_weff

    if p_hat >= 1.0:
        return {
            "snapshot_id": snapshot_id,
            "sell_through": 1.0,
            "sell_through_se": se,
            "adj_expected_return": None,
            "adj_expected_return_per_euro": None,
            "low_confidence": True,
            "retention_calibrated": calibrated,
        }

    if p_hat > HIGH_SELL_THROUGH_THRESHOLD:
        return _fallback(snapshot_id, prize_tiers, price, p_hat, empirical_retention, total_scenarios)

    # Clamp to avoid division blowup
    p_denom = min(p_hat, 0.9999)

    # Depletion-adjusted EV
    obs_amounts = {o["amt"] for o in observable}
    ev_adj = 0.0

    for o in observable:
        tier = o["tier"]
        w_i = tier["occurrences"]
        c_lifetime = min(w_i, o["c_i"] * elapsed_days / o["w_eff"])
        remaining = (w_i - c_lifetime) / (total_scenarios * (1 - p_denom))
        ev_adj += remaining * tier["prize_amount"]

    for tier in prize_tiers:
        if float(tier["prize_amount"]) not in obs_amounts:
            # non-observable: model-based, (1−p̂) cancels
            ev_adj += (tier["occurrences"] / total_scenarios) * tier["prize_amount"]

    ev_adj -= price
    ev_adj_per_euro = ev_adj / price

    return {
        "snapshot_id": snapshot_id,
        "sell_through": p_hat,
        "sell_through_se": se,
        "adj_expected_return": ev_adj,
        "adj_expected_return_per_euro": ev_adj_per_euro,
        "low_confidence": False,
        "retention_calibrated": calibrated,
    }


def _fallback(
    snapshot_id: str,
    prize_tiers: list[dict],
    price: float,
    p_hat: float | None,
    empirical_retention: dict | None,
    total_scenarios: int | None = None,
) -> dict[str, Any]:
    from .ev import baseline_ev
    # Prefer the authoritative total_scenarios from the snapshot. Only sum prize-tier
    # occurrences as a last resort — that count omits losing tickets and yields a
    # wildly inflated EV. (See the per-€1 = +1.6 vs −0.4 incident in early dev.)
    total = total_scenarios or (sum(t["occurrences"] for t in prize_tiers) if prize_tiers else 0)
    base_ev, base_ev_per_euro = (None, None)
    if prize_tiers and total > 0:
        base_ev, base_ev_per_euro = baseline_ev(prize_tiers, total, price)

    return {
        "snapshot_id": snapshot_id,
        "sell_through": p_hat,
        "sell_through_se": None,
        "adj_expected_return": base_ev,
        "adj_expected_return_per_euro": base_ev_per_euro,
        "low_confidence": True,
        "retention_calibrated": is_calibrated(empirical_retention),
    }
