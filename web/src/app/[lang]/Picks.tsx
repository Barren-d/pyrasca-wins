"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Locale } from "@/i18n/config";
import type { Dictionary } from "@/i18n/dictionaries";
import type { Ticket } from "@/lib/data";
import { fill, formatters } from "@/lib/format";
import { Chip, HeadRow, Table, Td, Th } from "@/components/Table";

// Avoid lists only tickets at least 3 cents per €1 worse than the best pick, so
// near-ties never show up there. An Avoid row 15 cents or more below the typical
// (median) ticket at the chosen price is flagged as an outlier.
const AVOID_GAP = 0.03;
const OUTLIER_GAP = 0.15;
// A drop of half a cent or more from on-paper to adjusted means big prizes are gone.
const CLAIMED_DROP = 0.005;

type Props = {
  locale: Locale;
  tickets: Ticket[]; // sorted by adjusted return, best first
  dict: Pick<Dictionary, "home" | "table" | "chips">;
};

export function Picks({ locale, tickets, dict }: Props) {
  const [price, setPrice] = useState<"all" | number>("all");
  const fmt = useMemo(() => formatters(locale), [locale]);
  const prices = useMemo(() => [...new Set(tickets.map((t) => t.price))].sort((a, b) => b - a), [tickets]);

  const list = price === "all" ? tickets : tickets.filter((t) => t.price === price);
  const n = list.length;
  const topN = price === "all" ? 8 : Math.min(5, Math.ceil(n / 2));
  const avoidN = price === "all" ? 3 : Math.min(3, n - topN);
  const picks = list.slice(0, topN);

  const best = n > 0 ? list[0].adjusted : 0;
  const candidates = list
    .map((t, i) => ({ t, rank: i + 1 }))
    .filter((x) => x.rank > topN && x.t.adjusted <= best - AVOID_GAP + 1e-9);
  const avoid = candidates.slice(Math.max(0, candidates.length - avoidN));
  const typical = median(list.map((t) => t.adjusted));
  const priceLabel = price === "all" ? dict.home.anyPriceLong : fmt.ticket(price);

  const href = (t: Ticket) => `/${locale}/games/${t.gameId}/${t.price}`;
  const endChip = (t: Ticket) =>
    t.saleEnd ? fill(dict.chips.ends, { date: fmt.dayMonth(t.saleEnd) }) : t.lastDays ? dict.chips.lastDays : null;

  return (
    <>
      <section className="flex flex-col gap-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex flex-wrap items-center gap-4">
            <h2 className="m-0 font-display text-[28px] font-semibold tracking-[-0.02em]">{dict.home.topPicks}</h2>
            <label className="flex items-center gap-2 text-sm text-muted">
              {dict.home.ticketPrice}
              <select
                value={String(price)}
                onChange={(e) => setPrice(e.target.value === "all" ? "all" : Number(e.target.value))}
                className="min-h-10 cursor-pointer rounded-lg border border-control bg-card pr-8 pl-3 text-[15px] font-semibold text-ink"
              >
                <option value="all">{dict.home.anyPrice}</option>
                {prices.map((p) => (
                  <option key={p} value={String(p)}>
                    {fmt.ticket(p)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <Link href={`/${locale}/games`} className="text-[15px] font-semibold text-link hover:text-ink">
            {fill(dict.home.seeAll, { n: tickets.length })}
          </Link>
        </div>

        <Table>
          <thead>
            <HeadRow>
              <Th className="w-10 pl-5">{dict.table.rank}</Th>
              <Th left>{dict.table.game}</Th>
              <Th>{dict.table.ticket}</Th>
              <Th>{dict.table.onPaper}</Th>
              <Th>{dict.table.adjusted}</Th>
              <Th className="pr-5">{dict.table.sold}</Th>
            </HeadRow>
          </thead>
          <tbody>
            {picks.map((t, i) => {
              const end = endChip(t);
              return (
                <tr key={`${t.gameId}-${t.price}`} className="num text-right">
                  <Td className="pl-5 text-muted">{i + 1}</Td>
                  <Td left>
                    <div className="flex flex-wrap items-center gap-2.5">
                      <Link href={href(t)} className="font-semibold text-ink no-underline hover:underline">
                        {t.name}
                      </Link>
                      {t.paper - t.adjusted >= CLAIMED_DROP && <Chip tone="warn">{dict.chips.topClaimed}</Chip>}
                      {end && <Chip tone="neutral">{end}</Chip>}
                    </div>
                  </Td>
                  <Td>{fmt.ticket(t.price)}</Td>
                  <Td className="text-muted">{fmt.perEuro(t.paper)}</Td>
                  <Td className="font-semibold">{fmt.perEuro(t.adjusted)}</Td>
                  <Td className="pr-5 text-muted">{t.soldShare === null ? "—" : fmt.pct(t.soldShare)}</Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <h2 className="m-0 font-display text-[28px] font-semibold tracking-[-0.02em]">{dict.home.avoid}</h2>
          <p className="num m-0 text-[15px] leading-normal text-muted">
            {avoid.length > 0
              ? dict.home.avoidIntro
              : fill(n <= 1 ? dict.home.avoidOnlyOne : dict.home.avoidNothing, { price: priceLabel })}
          </p>
        </div>
        {avoid.length > 0 && (
          <Table>
            <thead>
              <HeadRow>
                <Th className="w-10 pl-5">{dict.table.rank}</Th>
                <Th left>{dict.table.game}</Th>
                <Th>{dict.table.ticket}</Th>
                <Th>{dict.table.onPaper}</Th>
                <Th>{dict.table.adjusted}</Th>
                <Th left className="pr-5">
                  {dict.table.why}
                </Th>
              </HeadRow>
            </thead>
            <tbody>
              {avoid.map(({ t, rank }) => {
                const outlier = typical - t.adjusted >= OUTLIER_GAP;
                const reason = outlier
                  ? fill(dict.home.typical, { value: fmt.perEuro(typical) })
                  : t.paper - t.adjusted >= CLAIMED_DROP
                    ? dict.home.bigClaimed
                    : dict.home.weaker;
                return (
                  <tr key={`${t.gameId}-${t.price}`} className="num text-right">
                    <Td className="pl-5 text-muted">{rank}</Td>
                    <Td left>
                      <Link href={href(t)} className="font-semibold text-ink no-underline hover:underline">
                        {t.name}
                      </Link>
                    </Td>
                    <Td>{fmt.ticket(t.price)}</Td>
                    <Td className="text-muted">{fmt.perEuro(t.paper)}</Td>
                    <Td className="font-semibold text-warn">{fmt.perEuro(t.adjusted)}</Td>
                    <Td left className="pr-5 text-muted">
                      <div className="flex flex-wrap items-center gap-2">
                        {outlier && <Chip tone="strong">{dict.home.outlier}</Chip>}
                        <span>{reason}</span>
                      </div>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </section>
    </>
  );
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const s = [...values].sort((a, b) => a - b);
  const mid = s.length / 2;
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[mid - 1] + s[mid]) / 2;
}
