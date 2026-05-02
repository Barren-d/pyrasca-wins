from __future__ import annotations

import os
import subprocess
import sys
sys.stdout.reconfigure(encoding="utf-8")

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from src.db.client import get_client
from src.analysis.retention import retention_days

st.set_page_config(page_title="pyRasca", page_icon="🎟️", layout="wide")

BASE_URL = "https://www.juegosonce.es"
PRICE_OPTIONS = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_latest_snapshots() -> pd.DataFrame:
    client = get_client()

    # Two separate queries — more reliable than embedded join with supabase-py
    snap_rows = (
        client.table("game_snapshots")
        .select(
            "snapshot_id, game_id, scraped_at, price, "
            "total_scenarios, winning_scenarios, losing_scenarios, "
            "expected_return_per_euro, adj_expected_return_per_euro, "
            "sell_through, sell_through_se, low_confidence, retention_calibrated"
        )
        .order("scraped_at", desc=True)
        .limit(2000)
        .execute()
        .data
    )
    if not snap_rows:
        return pd.DataFrame()

    df = pd.DataFrame(snap_rows)

    game_ids = df["game_id"].dropna().unique().tolist()
    games_rows = (
        client.table("games")
        .select("game_id, name, img_url, url, game_start, first_seen")
        .in_("game_id", game_ids)
        .execute()
        .data
    )
    if games_rows:
        games_df = pd.DataFrame(games_rows).rename(
            columns={"url": "game_url", "first_seen": "scrape_first_seen"}
        )
        df = df.merge(games_df, on="game_id", how="left")
    else:
        df["name"] = None
        df["img_url"] = None
        df["game_url"] = None
        df["game_start"] = None
        df["scrape_first_seen"] = None

    # keep only the latest snapshot per game × price
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)
    df = df.sort_values("scraped_at", ascending=False)
    df = df.drop_duplicates(subset=["game_id", "price"], keep="first")

    df["ev_adj"] = pd.to_numeric(df["adj_expected_return_per_euro"], errors="coerce")
    df["ev_base"] = pd.to_numeric(df["expected_return_per_euro"], errors="coerce")
    df["sell_through"] = pd.to_numeric(df["sell_through"], errors="coerce")
    df["sell_through_se"] = pd.to_numeric(df["sell_through_se"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def load_ev_history(game_id: str) -> pd.DataFrame:
    client = get_client()
    rows = (
        client.table("game_snapshots")
        .select("scraped_at, ev_recomputed_at, price, expected_return_per_euro, adj_expected_return_per_euro")
        .eq("game_id", game_id)
        .order("scraped_at")
        .execute()
        .data
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)
    df["ev_recomputed_at"] = pd.to_datetime(df.get("ev_recomputed_at"), utc=True, errors="coerce")
    # x-axis: claimed-scrape recompute time when available, else original snapshot time
    df["as_of"] = df["ev_recomputed_at"].fillna(df["scraped_at"])
    df["ev_base"] = pd.to_numeric(df["expected_return_per_euro"], errors="coerce")
    df["ev_adj"] = pd.to_numeric(df["adj_expected_return_per_euro"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_prize_tiers(snapshot_id: str) -> pd.DataFrame:
    client = get_client()
    rows = (
        client.table("prize_tiers")
        .select("prize_amount, occurrences, is_annuity, annuity_years, annuity_annual_payment")
        .eq("snapshot_id", snapshot_id)
        .order("prize_amount", desc=True)
        .execute()
        .data
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_claimed_for_game(game_id: str) -> pd.DataFrame:
    client = get_client()
    rows = (
        client.table("claimed_prizes")
        .select("prize_amount, prize_amount_raw, winner, claimed_at, prize_tier_id")
        .eq("game_id", game_id)
        .order("claimed_at", desc=True)
        .limit(200)
        .execute()
        .data
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["claimed_at"] = pd.to_datetime(df["claimed_at"], utc=True)
    df["prize_amount"] = pd.to_numeric(df["prize_amount"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_recent_wins(min_prize: float = 500.0, limit: int = 100) -> pd.DataFrame:
    client = get_client()
    rows = (
        client.table("claimed_prizes")
        .select("game_name, game_url, prize_amount, winner, claimed_at")
        .gte("prize_amount", min_prize)
        .order("claimed_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["claimed_at"] = pd.to_datetime(df["claimed_at"], utc=True)
    df["prize_amount"] = pd.to_numeric(df["prize_amount"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_last_scrape() -> dict:
    client = get_client()
    rows = (
        client.table("scrape_runs")
        .select("run_type, completed_at, status, games_scraped")
        .order("started_at", desc=True)
        .limit(10)
        .execute()
        .data
    )
    result = {"full": None, "claimed": None}
    for row in rows:
        rt = row["run_type"]
        if result[rt] is None:
            result[rt] = row
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def confidence_badge(row: pd.Series) -> str:
    if row.get("low_confidence"):
        return "🔴 Insufficient data"
    if not row.get("retention_calibrated"):
        return "🟡 Calibrating"
    return "🟢"


def format_sell_through(sell: float | None, low_confidence: bool = False) -> str:
    """Render sell-through as a percentage. Flag age-prior estimates with an 'est.'
    prefix so users don't mistake fallback values for measurements."""
    if sell is None or pd.isna(sell):
        return "—"
    pct = sell * 100
    return f"est. {pct:.1f}%" if low_confidence else f"{pct:.1f}%"


def ev_color(ev_per_euro: float | None) -> str:
    if ev_per_euro is None:
        return "gray"
    if ev_per_euro >= -0.15:
        return "green"
    if ev_per_euro >= -0.30:
        return "orange"
    return "red"


def prize_status(
    prize_amount: float,
    claimed_df: pd.DataFrame,
    occurrences: int,
    elapsed_days: int | None = None,
    scraping_days: int | None = None,
) -> str:
    """Display status for a prize tier.

    'CLAIMED' / 'N of M remaining' = direct evidence from claimed_prizes.
    'Available' = zero claims observed AND our observation window covers the
        prize's full carousel-retention lifetime.
    'Unknown' = zero claims observed BUT the game launched before our scraping
        started AND retention isn't long enough to bridge the gap, so the prize
        may have been won before we could see it.
    """
    count = 0 if claimed_df.empty else len(claimed_df[claimed_df["prize_amount"] == prize_amount])
    if count >= occurrences:
        return "CLAIMED"
    if count > 0:
        return f"{occurrences - count} of {occurrences} remaining"

    # Zero observed claims — is our observation window deep enough to trust that?
    if elapsed_days is not None and scraping_days is not None:
        ret = retention_days(prize_amount)
        # Any claim from an elapsed window smaller than retention would still be
        # visible in the carousel right now, so Available is safe regardless of
        # when we started scraping.
        if elapsed_days > ret and scraping_days + ret < elapsed_days:
            return "Unknown"
    return "Available"


def observation_window(row: pd.Series) -> tuple[int | None, int | None]:
    """(elapsed_days, scraping_days) for a snapshot row, or (None, None) if missing."""
    today = datetime.now(timezone.utc)
    gs = pd.to_datetime(row.get("game_start"), utc=True, errors="coerce")
    fs = pd.to_datetime(row.get("scrape_first_seen"), utc=True, errors="coerce")
    if pd.isna(gs):
        return None, None
    elapsed = (today - gs.to_pydatetime()).days
    scraping = (today - fs.to_pydatetime()).days if not pd.isna(fs) else 0
    return max(elapsed, 0), max(scraping, 0)


def days_ago(dt) -> str:
    if pd.isna(dt):
        return "—"
    delta = datetime.now(timezone.utc) - dt.to_pydatetime()
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        m = total_seconds // 60
        return f"{m} min ago"
    if total_seconds < 86400:
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        return f"{h}h {m}m ago" if m else f"{h}h ago"
    d = delta.days
    if d == 1:
        return "yesterday"
    return f"{d} days ago"


# ── Bootstrap banner ──────────────────────────────────────────────────────────

def maybe_show_bootstrap_banner(df: pd.DataFrame) -> None:
    if df.empty:
        return
    pct_calibrated = df["retention_calibrated"].mean() if "retention_calibrated" in df else 0
    if pct_calibrated < 0.8:
        st.warning(
            "**EV adjustments are calibrating.** The retention model will be empirically "
            "fitted after ~30 days of carousel observation. Grand-prize depletion signals "
            "are reliable now; mid-tier signals may be biased.",
            icon="📊",
        )


# ── Page: Today's Picks ───────────────────────────────────────────────────────

def page_picks(df: pd.DataFrame) -> None:
    st.title("Today's Best Picks")

    if df.empty or "price" not in df.columns:
        st.info("No data available yet — run the scraper first.")
        return

    with st.sidebar:
        st.header("Filter by price")
        available_prices = sorted(df["price"].dropna().unique().tolist(), reverse=True)
        price_filter = st.selectbox("Ticket price (€)", ["All"] + [str(p) for p in available_prices])

    filtered = df.copy()
    if price_filter != "All":
        filtered = filtered[filtered["price"] == float(price_filter)]

    filtered = filtered.dropna(subset=["ev_adj"]).sort_values("ev_adj", ascending=False)
    top = filtered.head(5)

    if top.empty:
        st.info("No data available yet — run the scraper first.")
        return

    for _, row in top.iterrows():
        _render_pick_card(row)


def _render_pick_card(row: pd.Series) -> None:
    claimed_df = load_claimed_for_game(row["game_id"])
    tiers_df = load_prize_tiers(row["snapshot_id"])

    with st.container(border=True):
        col1, col2 = st.columns([1, 4])
        with col1:
            if row.get("img_url"):
                st.image(row["img_url"], width=80)
        with col2:
            game_url = row.get("game_url") or "#"
            st.markdown(f"### [{row['name']}]({game_url}) · €{row['price']:.2f}")

            ev = row["ev_adj"]
            ev_base = row["ev_base"]
            delta = (ev - ev_base) if (ev is not None and ev_base is not None) else None
            delta_str = f"  ({'↑' if delta >= 0 else '↓'} {abs(delta):.3f} vs baseline)" if delta is not None else ""

            st.markdown(
                f"**Return per €1:** `{ev:.3f}`{delta_str}"
            )

            sell = row.get("sell_through")
            se = row.get("sell_through_se")
            low_conf = bool(row.get("low_confidence"))
            if sell is not None:
                if low_conf:
                    label = f"{format_sell_through(sell, True)} sold"
                else:
                    se_pct = (se * 100) if se else 0
                    label = f"{format_sell_through(sell, False)} sold ± {se_pct:.1f}%"
                st.progress(min(1.0, sell), text=label)

            # top 2 prize status
            if not tiers_df.empty:
                elapsed, scraping = observation_window(row)
                top_tiers = tiers_df.nlargest(2, "prize_amount")
                for _, tier in top_tiers.iterrows():
                    status = prize_status(
                        tier["prize_amount"], claimed_df, int(tier["occurrences"]),
                        elapsed_days=elapsed, scraping_days=scraping,
                    )
                    if status == "Available":
                        icon, color = "✦", "green"
                    elif status == "CLAIMED":
                        icon, color = "✗", "red"
                    elif status == "Unknown":
                        icon, color = "?", "gray"
                    else:
                        icon, color = "◑", "orange"
                    label = f"**€{tier['prize_amount']:,.0f}** — :{color}[{status}]"
                    st.markdown(f"{icon} {label}")

            st.caption(confidence_badge(row))


# ── Page: All Games ───────────────────────────────────────────────────────────

def page_all_games(df: pd.DataFrame) -> None:
    st.title("All Games")

    if df.empty or "price" not in df.columns:
        st.info("No data yet.")
        return

    display = df.copy().dropna(subset=["ev_adj"]).sort_values("ev_adj", ascending=False).reset_index(drop=True)

    display["Confidence"] = display.apply(confidence_badge, axis=1)
    display["EV adj"] = display["ev_adj"].map(lambda x: f"{x:.3f}" if x is not None else "—")
    display["EV base"] = display["ev_base"].map(lambda x: f"{x:.3f}" if x is not None else "—")
    display["Sold %"] = display.apply(
        lambda r: format_sell_through(r["sell_through"], bool(r.get("low_confidence"))),
        axis=1,
    )
    display["Started"] = pd.to_datetime(display["game_start"], utc=True, errors="coerce").dt.date

    table_height = 38 + 35 * len(display)
    event = st.dataframe(
        display[["name", "price", "Started", "EV base", "EV adj", "Sold %", "Confidence"]].rename(
            columns={"name": "Game", "price": "Price (€)"}
        ),
        use_container_width=True,
        hide_index=True,
        height=table_height,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Started": st.column_config.DateColumn("Started", format="DD MMM YYYY"),
        },
    )

    selected_rows = event.selection.rows
    if selected_rows:
        st.session_state["_pending_nav_page"] = "Game Detail"
        st.session_state["_pending_game_name"] = display.iloc[selected_rows[0]]["name"]
        st.rerun()


# ── Page: Game Detail ─────────────────────────────────────────────────────────

def page_game_detail(game_id: str, df: pd.DataFrame) -> None:
    game_rows = df[df["game_id"] == game_id]
    if game_rows.empty:
        st.error("Game not found.")
        return

    row = game_rows.sort_values("price").iloc[0]
    title_col, btn_col = st.columns([6, 1])
    title_col.title(row["name"])
    game_url = row.get("game_url") or "#"
    btn_col.link_button("▶ Play", game_url, use_container_width=True)

    # price tab selector
    prices = sorted(game_rows["price"].tolist())
    price_labels = [f"€{p:.2f}" for p in prices]
    selected_idx = st.radio("Price tier", range(len(prices)), format_func=lambda i: price_labels[i], horizontal=True)
    snap_row = game_rows[game_rows["price"] == prices[selected_idx]].iloc[0]
    snapshot_id = snap_row["snapshot_id"]

    # header metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("EV adj (per €1)", f"{snap_row['ev_adj']:.3f}" if snap_row["ev_adj"] is not None else "—")
    c2.metric("EV base (per €1)", f"{snap_row['ev_base']:.3f}" if snap_row["ev_base"] is not None else "—")
    sell = snap_row.get("sell_through")
    low_conf = bool(snap_row.get("low_confidence"))
    c3.metric("Sell-through", format_sell_through(sell, low_conf))
    c4.markdown(f"**Confidence:** {confidence_badge(snap_row)}")

    # sell-through progress bar
    if sell is not None:
        if low_conf:
            text = f"Prize pool {format_sell_through(sell, True)} claimed"
        else:
            se = snap_row.get("sell_through_se") or 0
            text = f"Prize pool {format_sell_through(sell, False)} claimed ± {se*100:.1f}%"
        st.progress(min(1.0, sell), text=text)

    st.divider()

    # prize tier table
    st.subheader("Prize tiers")
    tiers_df = load_prize_tiers(snapshot_id)
    claimed_df = load_claimed_for_game(game_id)

    total_raw = snap_row.get("total_scenarios")
    total = int(total_raw) if total_raw and not pd.isna(total_raw) else None

    if not tiers_df.empty:
        total = total or sum(int(t["occurrences"]) for _, t in tiers_df.iterrows())
        elapsed, scraping = observation_window(snap_row)
        rows_out = []
        for _, tier in tiers_df.iterrows():
            amt = float(tier["prize_amount"])
            occ = int(tier["occurrences"])
            status = prize_status(amt, claimed_df, occ, elapsed_days=elapsed, scraping_days=scraping)
            claimed_count = len(claimed_df[claimed_df["prize_amount"] == amt]) if not claimed_df.empty else 0
            odds = f"1 in {total // occ:,}" if occ > 0 else "—"
            rows_out.append({
                "Prize": f"€{amt:,.2f}" + (" /yr" if tier.get("is_annuity") else ""),
                "Tickets": occ,
                "Est. Claimed": claimed_count if claimed_count else "—",
                "Status": status,
                "Odds": odds,
            })
        tier_display = pd.DataFrame(rows_out)

        def _style_status(val):
            if val == "CLAIMED":
                return "color: red; text-decoration: line-through"
            if val == "Available":
                return "color: green"
            if val == "Unknown":
                return "color: gray"
            return "color: orange"

        st.dataframe(
            tier_display.style.map(_style_status, subset=["Status"]),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # EV over time chart
    st.subheader("EV over time")
    hist = load_ev_history(game_id)
    if not hist.empty:
        price_hist = hist[hist["price"] == prices[selected_idx]]
        if not price_hist.empty:
            chart_data = price_hist.set_index("as_of")[["ev_base", "ev_adj"]]
            st.line_chart(chart_data, color=["#888888", "#1f77b4"])
            st.caption("Grey = baseline EV · Blue = adjusted EV (as of last claimed scrape)")

    st.divider()

    # claimed prizes log
    st.subheader("Claimed prizes — this game")
    if not claimed_df.empty:
        top_amounts = set(tiers_df.nlargest(2, "prize_amount")["prize_amount"].tolist()) if not tiers_df.empty else set()
        log = claimed_df[["prize_amount", "winner", "claimed_at"]].copy()
        log["Days ago"] = log["claimed_at"].apply(days_ago)
        log["Prize"] = log["prize_amount"].apply(lambda x: f"€{x:,.2f}")
        log["Notable"] = log["prize_amount"].isin(top_amounts)
        st.dataframe(
            log[["Prize", "winner", "Days ago"]].rename(columns={"winner": "Winner"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No claimed prizes recorded for this game yet.")


# ── Page: Recent Wins ─────────────────────────────────────────────────────────

_SCRAPE_CWD = os.path.dirname(os.path.abspath(__file__))


def page_recent_wins(min_prize: int = 500, run_clicked: bool = False) -> None:
    st.title("Recent Wins Feed")

    if run_clicked:
        with st.spinner("Running claimed scrape…"):
            result = subprocess.run(
                [sys.executable, "scrape.py", "--mode", "claimed"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=_SCRAPE_CWD,
            )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            output += "\nSTDERR:\n" + result.stderr.strip()
        st.session_state["scraper_log"] = output
        st.cache_data.clear()
        st.rerun()

    wins_df = load_recent_wins(min_prize=float(min_prize))

    if wins_df.empty:
        st.info("No wins matching this filter yet.")
    else:
        wins_df["When"] = wins_df["claimed_at"].apply(days_ago)
        wins_df["Prize"] = wins_df["prize_amount"].apply(
            lambda x: f"€{x:,.0f}" if x >= 1000 else f"€{x:,.2f}"
        )
        st.dataframe(
            wins_df[["game_name", "Prize", "winner", "claimed_at", "When"]].rename(
                columns={"game_name": "Game", "winner": "Winner", "claimed_at": "Date"}
            ),
            column_config={
                "Date": st.column_config.DatetimeColumn(
                    "Date", format="D MMM YYYY, HH:mm", timezone="UTC"
                ),
            },
            use_container_width=True,
            hide_index=True,
        )

    if "scraper_log" in st.session_state:
        st.divider()
        st.subheader("Last scrape log")
        st.code(st.session_state["scraper_log"], language=None)


# ── Navigation & main ─────────────────────────────────────────────────────────

def main() -> None:
    if "_pending_nav_page" in st.session_state:
        st.session_state["nav_page"] = st.session_state.pop("_pending_nav_page")
    if "_pending_game_name" in st.session_state:
        st.session_state["selected_game_name"] = st.session_state.pop("_pending_game_name")

    df = load_latest_snapshots()
    selected_game_id: str | None = None
    rw_min_prize: int = 50
    run_clicked: bool = False

    with st.sidebar:
        with st.expander("🔍 Debug", expanded=False):
            import os
            key = os.environ.get("SUPABASE_KEY", "")
            st.write("SUPABASE_URL set:", bool(os.environ.get("SUPABASE_URL")))
            st.write("Key role:", "service_role" if "service_role" in key else ("anon" if "anon" in key else "unknown"))
            st.write("Key tail:", key[-8:] if key else "none")
            st.write("df shape:", df.shape)
            if st.button("Force reload"):
                st.cache_data.clear()
                st.rerun()

    maybe_show_bootstrap_banner(df)

    with st.sidebar:
        st.title("pyRasca")
        page = st.radio(
            "Navigate",
            ["Today's Picks", "All Games", "Game Detail", "Recent Wins"],
            label_visibility="collapsed",
            key="nav_page",
        )

        if page == "Game Detail" and not df.empty:
            st.divider()
            game_names = sorted(df["name"].dropna().unique().tolist())
            selected_name = st.selectbox("Select a game", ["—"] + game_names, key="selected_game_name")
            selected_game_id = (
                df[df["name"] == selected_name]["game_id"].iloc[0]
                if selected_name != "—" else None
            )

        if page == "Recent Wins":
            st.divider()
            rw_min_prize = st.select_slider(
                "Min prize (€)",
                options=[0, 5, 10, 25, 50, 100, 250, 500, 1000, 5000],
                value=50,
                format_func=lambda x: "All" if x == 0 else f"€{x:,}+",
                key="rw_min_prize",
            )
            run_clicked = st.button("↻ Run Scraper", use_container_width=True)

        # data health footer
        st.divider()
        with st.expander("Data health"):
            scrape_info = load_last_scrape()
            for run_type, info in scrape_info.items():
                if info:
                    completed = info.get("completed_at", "")[:16] if info.get("completed_at") else "—"
                    st.caption(f"**{run_type}**: {info['status']} · {completed}")
                else:
                    st.caption(f"**{run_type}**: no runs yet")

    if page == "Today's Picks":
        page_picks(df)
    elif page == "All Games":
        page_all_games(df)
    elif page == "Game Detail":
        if selected_game_id:
            page_game_detail(selected_game_id, df)
        else:
            st.title("Game Detail")
            st.info("Select a game from the sidebar.")
    elif page == "Recent Wins":
        page_recent_wins(rw_min_prize, run_clicked)


if __name__ == "__main__":
    main()
