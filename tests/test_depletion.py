"""Hand-computed scenarios for src/analysis/depletion.py.

The depletion math has several interlocking branches (sparse-data fallback,
high-p̂ fallback, normal observable case). Each test exercises one branch
with a scenario whose expected output is computed by hand in the docstring.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from src.analysis.depletion import compute_adj_ev


def _call(**overrides):
    """Default scenario kwargs; override per test."""
    today = date(2026, 4, 1)
    defaults = {
        "snapshot_id": "snap-1",
        "game_id": "G1",
        "price": 2.0,
        "prize_tiers": [
            {"occurrences": 10, "prize_amount": 5000.0},
            {"occurrences": 100, "prize_amount": 5.0},
        ],
        "claimed_prizes": [],
        "game_start": today - timedelta(days=30),
        "scrape_start": today - timedelta(days=30),
        "today": today,
        "empirical_retention": None,
        "total_scenarios": 1000,
    }
    defaults.update(overrides)
    return compute_adj_ev(**defaults)


class TestFallbackBranches:
    def test_no_game_start_returns_baseline(self):
        """Missing game_start → _fallback with p_hat=None returns base EV."""
        result = _call(game_start=None)
        # base ev: (10/1000)*5000 + (100/1000)*5 - 2 = 50 + 0.5 - 2 = 48.5
        assert math.isclose(result["adj_expected_return"], 48.5, rel_tol=1e-9)
        assert result["low_confidence"] is True
        assert result["sell_through"] is None

    def test_empty_prize_tiers_returns_none(self):
        """No prize tiers → fallback returns base_ev=None."""
        result = _call(prize_tiers=[], game_start=None)
        assert result["adj_expected_return"] is None
        assert result["adj_expected_return_per_euro"] is None
        assert result["low_confidence"] is True

    def test_zero_elapsed_days_returns_baseline(self):
        """elapsed_days <= 0 (game launches today) → fallback to baseline."""
        today = date(2026, 4, 1)
        result = _call(game_start=today, today=today)
        assert math.isclose(result["adj_expected_return"], 48.5, rel_tol=1e-9)
        assert result["low_confidence"] is True

    def test_sparse_claims_falls_back_to_baseline(self):
        """0 claims observed → sum_c < MIN_CLAIMS_FOR_RATE → _fallback.

        Should set p_hat from age prior (elapsed_days / 1825) and return EV_base.
        """
        today = date(2026, 4, 1)
        result = _call(
            claimed_prizes=[],
            game_start=today - timedelta(days=30),
            today=today,
        )
        # base ev still 48.5
        assert math.isclose(result["adj_expected_return"], 48.5, rel_tol=1e-9)
        assert result["low_confidence"] is True
        # age-prior p_hat = 30 / 1825 ≈ 0.01644
        assert math.isclose(result["sell_through"], 30 / 1825, rel_tol=1e-6)
        assert result["sell_through_se"] is None

    def test_short_scraping_history_falls_back(self):
        """scraping_days < 14 → fallback even with claims."""
        today = date(2026, 4, 1)
        # 5 matched claims of grand prize, but only 5 days of scraping
        claims = [
            {"prize_amount": 5000.0, "prize_tier_id": "t1"} for _ in range(5)
        ]
        result = _call(
            claimed_prizes=claims,
            game_start=today - timedelta(days=30),
            scrape_start=today - timedelta(days=5),  # only 5 days
            today=today,
        )
        assert result["low_confidence"] is True
        assert math.isclose(result["adj_expected_return"], 48.5, rel_tol=1e-9)


class TestObservableTierMath:
    def test_uniform_depletion_yields_baseline(self):
        """When observable tier depletes at exactly the global rate, EV_adj ≈ EV_base.

        Setup:
          T=1000, price=2
          tier1 (observable): W=10, prize=5000  (retention 7d)
          tier2 (observable): W=20, prize=2000  (retention 7d)
          tier3 (non-observable): W=100, prize=5
          elapsed = scraping = 30 days; w_eff = min(30, 30+7) = 30 for both
          5 matched claims at prize=5000, 10 matched claims at prize=2000

          sum_c = 15, sum_w_weff = 10*30 + 20*30 = 900
          p_hat = (15 * 30) / 900 = 0.5
          c_lifetime tier1 = min(10, 5*30/30) = 5  (= W*p_hat ✓)
          c_lifetime tier2 = min(20, 10*30/30) = 10 (= W*p_hat ✓)
          remaining_t1 = (10-5) / (1000*0.5) = 0.01 → 0.01*5000 = 50
          remaining_t2 = (20-10) / (1000*0.5) = 0.02 → 0.02*2000 = 40
          tier3 (non-obs): (100/1000)*5 = 0.5
          ev_adj = 50 + 40 + 0.5 - 2 = 88.5

          EV_base = (10/1000)*5000 + (20/1000)*2000 + (100/1000)*5 - 2
                  = 50 + 40 + 0.5 - 2 = 88.5
        """
        today = date(2026, 4, 1)
        tiers = [
            {"occurrences": 10, "prize_amount": 5000.0},
            {"occurrences": 20, "prize_amount": 2000.0},
            {"occurrences": 100, "prize_amount": 5.0},
        ]
        claims = (
            [{"prize_amount": 5000.0, "prize_tier_id": "t1"} for _ in range(5)]
            + [{"prize_amount": 2000.0, "prize_tier_id": "t2"} for _ in range(10)]
        )
        result = _call(
            prize_tiers=tiers,
            claimed_prizes=claims,
            game_start=today - timedelta(days=30),
            scrape_start=today - timedelta(days=30),
            today=today,
            total_scenarios=1000,
        )
        assert result["low_confidence"] is False
        assert math.isclose(result["sell_through"], 0.5, rel_tol=1e-9)
        assert math.isclose(result["adj_expected_return"], 88.5, rel_tol=1e-9)
        assert math.isclose(
            result["adj_expected_return_per_euro"], 88.5 / 2, rel_tol=1e-9
        )

    def test_differential_depletion_lowers_ev(self):
        """High-prize tier over-depleted → EV_adj < EV_base.

        Same two observable tiers, but tier1 has 6 claims (over-depleted)
        and tier2 has 0 (under-depleted). Net effect: high-prize tier is
        rarer than expected → EV drops.

        sum_c = 6, sum_w_weff = 10*30 + 20*30 = 900
        p_hat = (6 * 30) / 900 = 0.2
        c_lifetime t1 = min(10, 6*30/30) = 6
        c_lifetime t2 = min(20, 0) = 0
        remaining_t1 = (10-6) / (1000 * 0.8) = 0.005 → 0.005*5000 = 25
        remaining_t2 = (20-0) / (1000 * 0.8) = 0.025 → 0.025*2000 = 50
        tier3 (non-obs): 0.5
        ev_adj = 25 + 50 + 0.5 - 2 = 73.5

        Compare to EV_base = 88.5; EV_adj < EV_base by 15.
        """
        today = date(2026, 4, 1)
        tiers = [
            {"occurrences": 10, "prize_amount": 5000.0},
            {"occurrences": 20, "prize_amount": 2000.0},
            {"occurrences": 100, "prize_amount": 5.0},
        ]
        claims = [
            {"prize_amount": 5000.0, "prize_tier_id": "t1"} for _ in range(6)
        ]
        result = _call(
            prize_tiers=tiers,
            claimed_prizes=claims,
            game_start=today - timedelta(days=30),
            scrape_start=today - timedelta(days=30),
            today=today,
            total_scenarios=1000,
        )
        assert result["low_confidence"] is False
        assert math.isclose(result["sell_through"], 0.2, rel_tol=1e-9)
        assert math.isclose(result["adj_expected_return"], 73.5, rel_tol=1e-9)

    def test_unmatched_claims_ignored(self):
        """Claims with prize_tier_id=None are excluded from sum_c.

        Same setup as uniform-depletion test, but the 15 claims have
        prize_tier_id=None. sum_c becomes 0 → sparse fallback → EV_base.
        """
        today = date(2026, 4, 1)
        tiers = [
            {"occurrences": 10, "prize_amount": 5000.0},
            {"occurrences": 20, "prize_amount": 2000.0},
            {"occurrences": 100, "prize_amount": 5.0},
        ]
        claims = (
            [{"prize_amount": 5000.0, "prize_tier_id": None} for _ in range(5)]
            + [{"prize_amount": 2000.0, "prize_tier_id": None} for _ in range(10)]
        )
        result = _call(
            prize_tiers=tiers,
            claimed_prizes=claims,
            game_start=today - timedelta(days=30),
            scrape_start=today - timedelta(days=30),
            today=today,
            total_scenarios=1000,
        )
        # sparse fallback → EV_adj = EV_base = 88.5, low_confidence=True
        assert result["low_confidence"] is True
        assert math.isclose(result["adj_expected_return"], 88.5, rel_tol=1e-9)


class TestHighSellThroughGuard:
    def test_p_hat_above_threshold_falls_back(self):
        """p_hat > 0.95 → fallback (T(1−p̂) too small to trust).

        Tight setup: tiny W, many claims, short window → p_hat ≈ 1.
        """
        today = date(2026, 4, 1)
        tiers = [
            {"occurrences": 10, "prize_amount": 5000.0},
            {"occurrences": 100, "prize_amount": 5.0},
        ]
        # 9 of 10 grand prizes claimed in 30 days → p_hat = 0.9
        # We need p_hat > 0.95 — claim 10 of 10:
        claims = [{"prize_amount": 5000.0, "prize_tier_id": "t1"} for _ in range(10)]
        result = _call(
            prize_tiers=tiers,
            claimed_prizes=claims,
            game_start=today - timedelta(days=30),
            scrape_start=today - timedelta(days=30),
            today=today,
            total_scenarios=1000,
        )
        # p_hat hits 1.0 → early-return branch (sell_through=1.0, EV_adj=None)
        # OR HIGH_SELL_THROUGH_THRESHOLD path (low_confidence=True, EV=base)
        # Either way: depletion-EV is not produced.
        assert result["low_confidence"] is True

    def test_p_hat_at_one_yields_no_ev_adj(self):
        """p_hat == 1.0 → adj_expected_return is None (game effectively over)."""
        today = date(2026, 4, 1)
        tiers = [{"occurrences": 5, "prize_amount": 5000.0}]
        claims = [{"prize_amount": 5000.0, "prize_tier_id": "t1"} for _ in range(5)]
        result = _call(
            prize_tiers=tiers,
            claimed_prizes=claims,
            game_start=today - timedelta(days=30),
            scrape_start=today - timedelta(days=30),
            today=today,
            total_scenarios=1000,
        )
        assert result["low_confidence"] is True
        # Either the p_hat=1.0 branch (returns None) or HIGH_SELL_THROUGH (returns base).
        # Both are acceptable shutdown behaviours; just confirm we didn't compute a number
        # by dividing by something near zero.
        assert (
            result["adj_expected_return"] is None
            or math.isclose(result["adj_expected_return"], 23.0, rel_tol=1e-9)
        )
