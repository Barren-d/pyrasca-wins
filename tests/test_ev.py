"""Hand-computed arithmetic checks for src/analysis/ev.py."""
from __future__ import annotations

import math

import pytest

from src.analysis.ev import baseline_ev, annuity_pv


class TestBaselineEv:
    def test_typical_lottery_distribution(self):
        """Mostly losses, two prize tiers.

        T = 1000, price = 2
        Prize tiers: (W=1, €500), (W=10, €20)
        Gross = (1/1000)*500 + (10/1000)*20 = 0.5 + 0.2 = 0.7
        EV  = 0.7 − 2 = −1.3
        Per €: −0.65
        """
        tiers = [
            {"occurrences": 1, "prize_amount": 500},
            {"occurrences": 10, "prize_amount": 20},
        ]
        ev, ev_per_euro = baseline_ev(tiers, total_scenarios=1000, price=2.0)
        assert math.isclose(ev, -1.3, rel_tol=1e-9)
        assert math.isclose(ev_per_euro, -0.65, rel_tol=1e-9)

    def test_all_winning_sanity_check(self):
        """T = 10, all tickets are winners. Just confirms the arithmetic."""
        tiers = [
            {"occurrences": 1, "prize_amount": 100},
            {"occurrences": 9, "prize_amount": 5},
        ]
        ev, ev_per_euro = baseline_ev(tiers, total_scenarios=10, price=5.0)
        # gross = 10 + 4.5 = 14.5; ev = 9.5; per €1 = 1.9
        assert math.isclose(ev, 9.5, rel_tol=1e-9)
        assert math.isclose(ev_per_euro, 1.9, rel_tol=1e-9)

    def test_zero_prizes(self):
        """No winning tickets = pure loss of the ticket price."""
        ev, ev_per_euro = baseline_ev([], total_scenarios=1000, price=2.0)
        assert ev == -2.0
        assert ev_per_euro == -1.0


class TestAnnuityPV:
    def test_one_year_equals_discounted_pmt(self):
        """PV(pmt, 1 yr, r) = pmt / (1 + r)."""
        pv = annuity_pv(100.0, n=1, r=0.03)
        assert math.isclose(pv, 100.0 / 1.03, rel_tol=1e-9)

    def test_ten_year_at_three_percent(self):
        """Standard textbook number: PV(1000, 10, 0.03) ≈ 8530.20."""
        pv = annuity_pv(1000.0, n=10, r=0.03)
        assert math.isclose(pv, 8530.2028, rel_tol=1e-4)

    def test_pv_strictly_less_than_undiscounted_total(self):
        """For any r > 0, PV must be less than n × pmt."""
        pv = annuity_pv(500.0, n=20, r=0.03)
        assert pv < 500.0 * 20

    @pytest.mark.parametrize("years", [5, 10, 25, 50])
    def test_monotone_in_n(self, years):
        """PV grows with n (longer payments = higher PV) at fixed pmt + r."""
        smaller = annuity_pv(100.0, n=years, r=0.03)
        larger = annuity_pv(100.0, n=years + 1, r=0.03)
        assert larger > smaller
