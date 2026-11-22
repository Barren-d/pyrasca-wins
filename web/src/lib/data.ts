import "server-only";
import { cacheLife } from "next/cache";
import { count, select } from "./supabase";

// The claimed scrape runs about every 48 minutes and the full scrape weekly, so
// data cached for 10 minutes is never meaningfully stale.
const CACHE = { stale: 300, revalidate: 600, expire: 3600 };

/** One ticket on sale: a game at one ticket price (row of the game_overview view). */
export type Ticket = {
  gameId: string;
  name: string;
  price: number;
  paper: number; // payback per €1 from the prize table
  adjusted: number; // payback per €1 after prizes already claimed
  soldShare: number | null;
  lowConfidence: boolean;
  winChance: number | null; // share of tickets that win something
  onSaleSince: string | null; // official first day of sale, else the date on ONCE's site
  saleEnd: string | null; // ISO date, from ONCE's end-of-sale notice
  lastDays: boolean; // listing card says "¡Últimos días!"
};

type OverviewRow = {
  game_id: string;
  name: string;
  price: number;
  payback_per_euro: number | null;
  adj_payback_per_euro: number | null;
  sell_through: number | null;
  low_confidence: boolean | null;
  win_chance: number | null;
  game_start: string | null;
  sale_start: string | null;
  sale_end: string | null;
  listing_label: string | null;
};

// game_start is Spanish midnight stored in UTC (16 Feb → "2021-02-15T23:00Z")
const madridDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" });
const madridDate = (iso: string) => madridDay.format(new Date(iso)); // "2021-02-16"

export async function getTicketsOnSale(): Promise<Ticket[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<OverviewRow>(
    "game_overview?select=game_id,name,price,payback_per_euro,adj_payback_per_euro," +
      "sell_through,low_confidence,win_chance,game_start,sale_start,sale_end,listing_label&active=eq.true",
  );
  return rows
    .filter((r) => r.payback_per_euro !== null)
    .map((r) => ({
      gameId: r.game_id,
      name: r.name,
      price: Number(r.price),
      paper: Number(r.payback_per_euro),
      adjusted: Number(r.adj_payback_per_euro ?? r.payback_per_euro),
      soldShare: r.sell_through === null ? null : Number(r.sell_through),
      lowConfidence: !!r.low_confidence,
      winChance: r.win_chance === null ? null : Number(r.win_chance),
      onSaleSince: r.sale_start ?? (r.game_start ? madridDate(r.game_start) : null),
      saleEnd: r.sale_end,
      lastDays: /ltimos d/i.test(r.listing_label ?? ""),
    }))
    .sort((a, b) => b.adjusted - a.adjusted);
}

export async function getClaimCount(): Promise<number> {
  "use cache";
  cacheLife(CACHE);
  return count("claimed_prizes");
}

/** Completion time of the latest successful claimed scrape (ISO), if any. */
export async function getLastUpdate(): Promise<string | null> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<{ completed_at: string | null }>(
    "scrape_runs?select=completed_at&status=eq.success&completed_at=not.is.null&order=completed_at.desc&limit=1",
  );
  return rows[0]?.completed_at ?? null;
}

export type Win = {
  claimId: string;
  gameId: string | null;
  gameName: string;
  prize: number;
  ticketPrice: number | null;
  claimedAt: string;
};

type WinRow = {
  claim_id: string;
  game_id: string | null;
  game_name: string;
  prize_amount: number;
  ticket_price: number | null;
  claimed_at: string;
};

/** Largest wins of 5× the ticket or more claimed in the last 7 days. */
export async function getBiggestWinsThisWeek(limit = 4): Promise<Win[]> {
  "use cache";
  cacheLife(CACHE);
  const since = new Date(Date.now() - 7 * 86_400_000).toISOString();
  const rows = await select<WinRow>(
    "recent_wins?select=claim_id,game_id,game_name,prize_amount,ticket_price,claimed_at" +
      `&prize_multiple=gte.5&claimed_at=gte.${since}&order=prize_amount.desc,claimed_at.desc&limit=${limit}`,
  );
  return rows.map((r) => ({
    claimId: r.claim_id,
    gameId: r.game_id,
    gameName: r.game_name,
    prize: Number(r.prize_amount),
    ticketPrice: r.ticket_price === null ? null : Number(r.ticket_price),
    claimedAt: r.claimed_at,
  }));
}

// ─── Game page ──────────────────────────────────────────────────────────────────

/** One ticket price of a game, with everything the game page header needs. */
export type GamePrice = Ticket & {
  active: boolean;
  url: string;
  seriesSize: number | null;
  winningTickets: number | null;
  topPrize: number | null;
  topPrizesPrinted: number | null;
  topPrizesClaimed: number | null;
  lastSeen: string | null;
  endSourceUrl: string | null;
};

type GameRow = OverviewRow & {
  active: boolean;
  url: string;
  series_size: number | null;
  winning_scenarios: number | null;
  top_prize: number | null;
  top_prizes_printed: number | null;
  top_prizes_claimed: number | null;
  last_seen: string | null;
  end_source_url: string | null;
};

const num = (v: number | null) => (v === null ? null : Number(v));

/** Every ticket price of one game (active or not), highest price first. */
export async function getGame(gameId: string): Promise<GamePrice[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<GameRow>(
    "game_overview?select=game_id,name,price,payback_per_euro,adj_payback_per_euro,sell_through,low_confidence," +
      "win_chance,game_start,sale_start,sale_end,listing_label,active,url,series_size,winning_scenarios," +
      `top_prize,top_prizes_printed,top_prizes_claimed,last_seen,end_source_url&game_id=eq.${encodeURIComponent(gameId)}` +
      "&order=price.desc",
  );
  return rows.map((r) => ({
    gameId: r.game_id,
    name: r.name,
    price: Number(r.price),
    paper: Number(r.payback_per_euro ?? 0),
    adjusted: Number(r.adj_payback_per_euro ?? r.payback_per_euro ?? 0),
    soldShare: num(r.sell_through),
    lowConfidence: !!r.low_confidence,
    winChance: num(r.win_chance),
    onSaleSince: r.sale_start ?? (r.game_start ? madridDate(r.game_start) : null),
    saleEnd: r.sale_end,
    lastDays: /ltimos d/i.test(r.listing_label ?? ""),
    active: r.active,
    url: r.url,
    seriesSize: num(r.series_size),
    winningTickets: num(r.winning_scenarios),
    topPrize: num(r.top_prize),
    topPrizesPrinted: num(r.top_prizes_printed),
    topPrizesClaimed: num(r.top_prizes_claimed),
    lastSeen: r.last_seen,
    endSourceUrl: r.end_source_url,
  }));
}

/** Game ids for prerendering every game page at build time. */
export async function getAllGameIds(): Promise<string[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<{ game_id: string }>("game_overview?select=game_id");
  return [...new Set(rows.map((r) => r.game_id))];
}

export type Tier = {
  prize: number;
  printed: number;
  claimed: number;
  annuityYears: number | null;
  annuityPerYear: number | null;
};

export async function getPrizeTable(gameId: string, price: number): Promise<Tier[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<{
    prize_amount: number;
    occurrences: number;
    claims_seen: number;
    is_annuity: boolean | null;
    annuity_years: number | null;
    annuity_annual_payment: number | null;
  }>(
    "prize_table?select=prize_amount,occurrences,claims_seen,is_annuity,annuity_years,annuity_annual_payment" +
      `&game_id=eq.${encodeURIComponent(gameId)}&price=eq.${price}&order=prize_amount.desc`,
  );
  return rows.map((r) => ({
    prize: Number(r.prize_amount),
    printed: Number(r.occurrences),
    claimed: Number(r.claims_seen),
    annuityYears: r.is_annuity ? num(r.annuity_years) : null,
    annuityPerYear: r.is_annuity ? num(r.annuity_annual_payment) : null,
  }));
}

/** One point of the share-sold / adjusted-return history. */
export type HistoryPoint = { at: string; sold: number | null; adjusted: number | null };

export async function getHistory(gameId: string, price: number): Promise<HistoryPoint[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<{
    scraped_at: string;
    ev_recomputed_at: string | null;
    sell_through: number | null;
    adj_expected_return_per_euro: number | null;
  }>(
    "game_snapshots?select=scraped_at,ev_recomputed_at,sell_through,adj_expected_return_per_euro" +
      `&game_id=eq.${encodeURIComponent(gameId)}&price=eq.${price}&total_scenarios=not.is.null&order=scraped_at`,
  );
  // As in the dashboard: a point is dated when its estimate was last recomputed
  return rows
    .map((r) => ({
      at: r.ev_recomputed_at ?? r.scraped_at,
      sold: num(r.sell_through),
      adjusted: r.adj_expected_return_per_euro === null ? null : 1 + Number(r.adj_expected_return_per_euro),
    }))
    .sort((a, b) => a.at.localeCompare(b.at));
}

export type Claim = { claimId: string; prize: number; winner: string | null; claimedAt: string };

/** Latest claims on one game; for a multi-price game, those of this price or of unknown price. */
export async function getGameClaims(gameId: string, price: number, multiPrice: boolean, limit = 6): Promise<Claim[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<{ claim_id: string; prize_amount: number; winner: string | null; claimed_at: string }>(
    `recent_wins?select=claim_id,prize_amount,winner,claimed_at&game_id=eq.${encodeURIComponent(gameId)}` +
      (multiPrice ? `&or=(ticket_price.eq.${price},ticket_price.is.null)` : "") +
      `&order=claimed_at.desc&limit=${limit}`,
  );
  return rows.map((r) => ({ claimId: r.claim_id, prize: Number(r.prize_amount), winner: r.winner, claimedAt: r.claimed_at }));
}

// ─── Recent wins ────────────────────────────────────────────────────────────────

export type WinFilter = "all" | "x5" | "k1";

const WIN_FILTERS: Record<WinFilter, string> = {
  all: "",
  x5: "prize_multiple=gte.5", // 5× the ticket or more
  k1: "prize_amount=gte.1000",
};

export type FeedWin = Win & { winner: string | null };

/** Newest wins for one filter, and how many wins match it in total. */
export async function getRecentWins(filter: WinFilter, limit = 100): Promise<{ wins: FeedWin[]; total: number }> {
  "use cache";
  cacheLife(CACHE);
  const where = WIN_FILTERS[filter];
  const [rows, total] = await Promise.all([
    select<WinRow & { winner: string | null }>(
      "recent_wins?select=claim_id,game_id,game_name,winner,prize_amount,ticket_price,claimed_at" +
        `${where ? `&${where}` : ""}&order=claimed_at.desc&limit=${limit}`,
    ),
    count("recent_wins", where),
  ]);
  return {
    total,
    wins: rows.map((r) => ({
      claimId: r.claim_id,
      gameId: r.game_id,
      gameName: r.game_name,
      winner: r.winner,
      prize: Number(r.prize_amount),
      ticketPrice: r.ticket_price === null ? null : Number(r.ticket_price),
      claimedAt: r.claimed_at,
    })),
  };
}

/** Each game's own name (the winners list sometimes shortens it). */
export async function getGameNames(): Promise<Record<string, string>> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<{ game_id: string; name: string }>("games?select=game_id,name");
  return Object.fromEntries(rows.map((r) => [r.game_id, r.name]));
}

// ─── Archive ────────────────────────────────────────────────────────────────────

export type InactiveTicket = {
  gameId: string;
  name: string;
  price: number;
  launched: string | null; // official first day of sale, else ONCE's date (ISO day)
  ended: string; // last day we saw it on sale (ISO)
  paper: number | null;
  topPrize: number | null;
  topPrinted: number | null;
  topClaimed: number | null;
  /** A game on sale now that continues this one (same name, or same code with another theme). */
  relaunch: { gameId: string; name: string; since: string | null } | null;
};

type GameListRow = {
  game_id: string;
  name: string;
  prices: number[] | null;
  game_start: string | null;
  last_seen: string;
  active: boolean;
};

/** Theme suffixes (_01, _02, …) are skins of one product: "EF8_03" → "EF8". */
const baseCode = (gameId: string) => gameId.split("_")[0];
/** Name compared ignoring case and accents: "Súper" = "Super". */
export const sameName = (a: string, b: string) => {
  const norm = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
  return norm(a) === norm(b);
};

export async function getInactiveTickets(): Promise<InactiveTicket[]> {
  "use cache";
  cacheLife(CACHE);
  const [games, rows] = await Promise.all([
    select<GameListRow>("games?select=game_id,name,prices,game_start,last_seen,active"),
    select<{
      game_id: string;
      price: number;
      sale_start: string | null;
      payback_per_euro: number | null;
      top_prize: number | null;
      top_prizes_printed: number | null;
      top_prizes_claimed: number | null;
    }>(
      "game_overview?select=game_id,price,sale_start,payback_per_euro,top_prize,top_prizes_printed,top_prizes_claimed&active=eq.false",
    ),
  ]);
  const start = (g: GameListRow) => (g.game_start ? madridDate(g.game_start) : null);
  const active = games.filter((g) => g.active);
  const relaunchOf = (g: GameListRow) => {
    const s = start(g) ?? "";
    const next = active
      .filter((a) => (baseCode(a.game_id) === baseCode(g.game_id) || sameName(a.name, g.name)) && (start(a) ?? "") > s)
      .sort((a, b) => (start(a) ?? "").localeCompare(start(b) ?? ""))[0];
    return next ? { gameId: next.game_id, name: next.name, since: start(next) } : null;
  };

  const byId = new Map(games.map((g) => [g.game_id, g]));
  const withTable = new Set(rows.map((r) => r.game_id));
  const tickets: InactiveTicket[] = rows.flatMap((r) => {
    const g = byId.get(r.game_id);
    if (!g) return [];
    return [{
      gameId: g.game_id,
      name: g.name,
      price: Number(r.price),
      launched: r.sale_start ?? start(g),
      ended: g.last_seen,
      paper: num(r.payback_per_euro),
      topPrize: num(r.top_prize),
      topPrinted: num(r.top_prizes_printed),
      topClaimed: num(r.top_prizes_claimed),
      relaunch: relaunchOf(g),
    }];
  });
  // Inactive games whose prize table was never read still get a row
  for (const g of games) {
    if (g.active || withTable.has(g.game_id)) continue;
    for (const price of g.prices ?? []) {
      tickets.push({
        gameId: g.game_id, name: g.name, price: Number(price), launched: start(g), ended: g.last_seen,
        paper: null, topPrize: null, topPrinted: null, topClaimed: null, relaunch: relaunchOf(g),
      });
    }
  }
  return tickets.sort((a, b) => b.ended.localeCompare(a.ended) || b.price - a.price);
}
