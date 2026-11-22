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
  sale_end: string | null;
  listing_label: string | null;
};

export async function getTicketsOnSale(): Promise<Ticket[]> {
  "use cache";
  cacheLife(CACHE);
  const rows = await select<OverviewRow>(
    "game_overview?select=game_id,name,price,payback_per_euro,adj_payback_per_euro," +
      "sell_through,low_confidence,sale_end,listing_label&active=eq.true",
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
