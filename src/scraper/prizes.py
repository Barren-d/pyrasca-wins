from __future__ import annotations

import re
import sys
sys.stdout.reconfigure(encoding="utf-8")

from typing import Any

from bs4 import BeautifulSoup

from . import session

DISCOUNT_RATE = 0.03


def scrape_prizes(game_id: str, url: str, prices: list[float]) -> list[dict[str, Any]]:
    """Return one snapshot-dict per price tier for this game."""
    html = session.get(url)
    soup = BeautifulSoup(html, "lxml")
    return [_extract_price_tier(soup, game_id, url, price) for price in prices]


def _extract_price_tier(
    soup: BeautifulSoup, game_id: str, url: str, price: float
) -> dict[str, Any]:
    section_contents = soup.find_all("div", class_="contenido")

    header_text: str | None = None
    tier_ul = None

    for contents in section_contents:
        for h3 in contents.find_all("h3"):
            if _header_matches_price(h3.text, price):
                header_text = h3.text
                tier_ul = h3.find_next_sibling("ul")
                break  # Bug fix #2: stop at first match
        if header_text:
            break

    if header_text is None or tier_ul is None:
        return _empty_snapshot(game_id, price)

    total_scenarios = _parse_total_scenarios(header_text, price)
    raw_pairs = _parse_prize_pairs(tier_ul)

    winning_scenarios = sum(occ for occ, _ in raw_pairs)
    losing_scenarios = total_scenarios - winning_scenarios

    prize_tiers = [
        {
            "occurrences": occ,
            "prize_amount": amt,
            "is_annuity": False,
            "annuity_years": None,
            "annuity_annual_payment": None,
        }
        for occ, amt in raw_pairs
    ]

    gross_ev = sum(occ / total_scenarios * amt for occ, amt in raw_pairs)
    expected_return = gross_ev - price
    expected_return_per_euro = expected_return / price

    return {
        "game_id": game_id,
        "price": price,
        "total_scenarios": total_scenarios,
        "winning_scenarios": winning_scenarios,
        "losing_scenarios": losing_scenarios,
        "expected_return": expected_return,
        "expected_return_per_euro": expected_return_per_euro,
        "adj_expected_return": expected_return,
        "adj_expected_return_per_euro": expected_return_per_euro,
        "sell_through": None,
        "sell_through_se": None,
        "low_confidence": True,
        "retention_calibrated": False,
        "prize_tiers": prize_tiers,
    }


def _header_matches_price(header: str, price: float) -> bool:
    price_str = str(price).rstrip("0").rstrip(".")
    # format price as ONCE displays it (comma decimal for non-integers)
    if price != int(price):
        price_str = f"{price:.2f}".replace(".", ",")
    else:
        price_str = str(int(price))

    # exact match e.g. "10 €"
    if f"{price_str} €" in header:
        return True
    # Bug fix #1: only try 0-suffix match when price string contains a comma
    if "," in price_str and f"{price_str}0 €" in header:
        return True
    return False


def _parse_total_scenarios(header: str, price: float) -> int:
    price_str = str(int(price)) if price == int(price) else f"{price:.2f}".replace(".", ",")
    text = header
    for fragment in [
        f"{price_str} €",
        f"{price_str}0 €",
        "Premios por cada serie de boletos de ",
        "con precio a",
        " ",
        ":",
        ".",
    ]:
        text = text.replace(fragment, "")
    return int(text.strip())


def _parse_prize_pairs(ul) -> list[tuple[int, float]]:
    pairs: list[tuple[int, float]] = []
    for li in ul.find_all("li"):
        # Normalize non-breaking spaces so all string operations work uniformly
        text = li.get_text().replace("\xa0", " ")
        span = li.find("span")
        if not span:
            continue
        prize_raw = span.get_text().replace("\xa0", " ")

        prize_str = prize_raw.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
        # Bug fix #3: use float() not int() for prize amount
        prize_float = float(prize_str)

        # Handle annual annuity: "al año durante N años"
        annual_match = re.search(r"al año durante (\d{1,3}) años", text)
        # Handle monthly annuity: "al mes durante N años"
        monthly_match = re.search(r"al mes durante (\d{1,3}) años", text)

        if annual_match:
            n = int(annual_match.group(1))
            # Bug fix #4: pass discount_rate through to annuity calculation
            prize_float = _annuity_pv(prize_float, n, DISCOUNT_RATE)
            occ_text = text.replace(prize_raw, "").replace(annual_match.group(0), "")
        elif monthly_match:
            n = int(monthly_match.group(1))
            prize_float = _monthly_annuity_pv(prize_float, n, DISCOUNT_RATE)
            occ_text = text.replace(prize_raw, "").replace(monthly_match.group(0), "")
        else:
            occ_text = text.replace(prize_raw, "")

        # Some annuity tiers include a bonus lump sum: "+ 250.000 €"
        bonus_match = re.search(r"\+\s*([\d.]+(?:,\d+)?)\s*€", occ_text)
        if bonus_match:
            bonus = float(
                bonus_match.group(1).replace(".", "").replace(",", ".")
            )
            prize_float += bonus
            occ_text = occ_text[: bonus_match.start()] + occ_text[bonus_match.end():]

        occ_text = (
            occ_text.replace(" premios de ", "")
            .replace(" premio de ", "")
            .replace(".", "")
            .replace(",", "")
            .replace(" ", "")
            .strip(".")
            .strip()
        )

        try:
            occurrences = int(occ_text)
        except ValueError:
            continue  # skip malformed entries rather than crash

        pairs.append((occurrences, prize_float))

    return pairs


def _annuity_pv(pmt: float, n: int, r: float) -> float:
    return pmt * (1 - (1 + r) ** -n) / r


def _monthly_annuity_pv(pmt_monthly: float, n_years: int, r_annual: float) -> float:
    r_monthly = (1 + r_annual) ** (1 / 12) - 1
    n_months = n_years * 12
    return pmt_monthly * (1 - (1 + r_monthly) ** -n_months) / r_monthly


def _empty_snapshot(game_id: str, price: float) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "price": price,
        "total_scenarios": None,
        "winning_scenarios": None,
        "losing_scenarios": None,
        "expected_return": None,
        "expected_return_per_euro": None,
        "adj_expected_return": None,
        "adj_expected_return_per_euro": None,
        "sell_through": None,
        "sell_through_se": None,
        "low_confidence": True,
        "retention_calibrated": False,
        "prize_tiers": [],
    }
