from __future__ import annotations

from ..db.client import get_client

# Bootstrap defaults (days) until empirical curve is available.
# Calibrated conservatively against observed carousel retention data.
_DEFAULT_RETENTION: list[tuple[float, float]] = [
    (10_000.0, 30.0),
    (1_000.0,   7.0),
    (100.0,     1.0),
]
_DEFAULT_RETENTION_FALLBACK = 0.0

MIN_CLAIMS_FOR_CALIBRATION = 50


def retention_days(prize_amount: float, empirical: dict[float, float] | None = None) -> float:
    """Return retention estimate in days for the given prize amount.

    Uses empirical curve if provided, otherwise falls back to step-function default.
    """
    if empirical:
        # find the highest threshold ≤ prize_amount
        thresholds = sorted(empirical.keys(), reverse=True)
        for t in thresholds:
            if prize_amount >= t:
                return empirical[t]
        return _DEFAULT_RETENTION_FALLBACK

    for threshold, days in _DEFAULT_RETENTION:
        if prize_amount >= threshold:
            return days
    return _DEFAULT_RETENTION_FALLBACK


def load_empirical_retention() -> dict[float, float] | None:
    """Query claimed_prizes history to build an empirical retention curve.

    Returns a {prize_amount: retention_days} dict if enough data exists,
    else None (triggers bootstrap defaults).

    SQL: 90th-percentile of (last_seen − claimed_at) per prize_amount bucket,
    excluding entries still visible in the carousel (last_seen < now − 1h).
    """
    client = get_client()

    # Supabase does not expose WITHIN GROUP aggregates via the REST API.
    # Use rpc() calling a Postgres function defined once in Supabase:
    #
    #   CREATE OR REPLACE FUNCTION retention_curve()
    #   RETURNS TABLE(prize_amount NUMERIC, retention_days FLOAT) AS $$
    #     SELECT prize_amount,
    #            EXTRACT(EPOCH FROM percentile_disc(0.9) WITHIN GROUP (
    #                ORDER BY last_seen - claimed_at
    #            )) / 86400.0 AS retention_days
    #     FROM claimed_prizes
    #     WHERE last_seen < NOW() - INTERVAL '1 hour'
    #     GROUP BY prize_amount
    #     HAVING COUNT(*) >= 50
    #   $$ LANGUAGE SQL;
    #
    try:
        rows = client.rpc("retention_curve", {}).execute().data
    except Exception:
        return None

    if not rows:
        return None

    return {float(row["prize_amount"]): float(row["retention_days"]) for row in rows}


def is_calibrated(empirical: dict[float, float] | None) -> bool:
    return empirical is not None and len(empirical) > 0
