"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChoiceRow } from "@/components/ChoiceRow";
import { Chip, HeadRow, Table, Td, Th } from "@/components/Table";
import type { Locale } from "@/i18n/config";
import type { Dictionary } from "@/i18n/dictionaries";
import type { Ticket } from "@/lib/data";
import { fill, formatters } from "@/lib/format";

// Show the claimed-prizes line when big prizes cut the return by half a cent or more
const CLAIMED_DROP = 0.005;

type Sort = "best" | "newest" | "sold" | "ending";

type Props = {
  locale: Locale;
  tickets: Ticket[]; // sorted by adjusted return, best first
  dict: Pick<Dictionary, "allGames" | "table" | "chips">;
};

const byText = (a: string | null, b: string | null, missing: string) => (a ?? missing).localeCompare(b ?? missing);

const sorters: Record<Sort, (a: Ticket, b: Ticket) => number> = {
  best: (a, b) => b.adjusted - a.adjusted,
  newest: (a, b) => byText(b.onSaleSince, a.onSaleSince, ""),
  sold: (a, b) => (b.soldShare ?? -1) - (a.soldShare ?? -1),
  // Announced end dates first (soonest first), then "last days" without a date, then the rest
  ending: (a, b) => byText(a.saleEnd, b.saleEnd, "9999") || Number(b.lastDays) - Number(a.lastDays) || b.adjusted - a.adjusted,
};

export function AllGamesTable({ locale, tickets, dict }: Props) {
  const t = dict.allGames;
  const [price, setPrice] = useState<"all" | number>("all");
  const [sort, setSort] = useState<Sort>("best");
  const fmt = useMemo(() => formatters(locale), [locale]);
  const prices = useMemo(() => [...new Set(tickets.map((x) => x.price))].sort((a, b) => b - a), [tickets]);

  const rows = (price === "all" ? tickets : tickets.filter((x) => x.price === price)).slice().sort(sorters[sort]);
  const sorts: { id: Sort; label: string }[] = [
    { id: "best", label: t.sortBest },
    { id: "newest", label: t.sortNewest },
    { id: "sold", label: t.sortSold },
    { id: "ending", label: t.sortEnding },
  ];

  return (
    <>
      <section aria-label={t.ticketPrice} className="flex flex-col gap-4">
        <ChoiceRow label={t.ticketPrice}>
          <Pill on={price === "all"} onClick={() => setPrice("all")}>
            {t.all}
          </Pill>
          {prices.map((p) => (
            <Pill key={p} on={price === p} onClick={() => setPrice(p)}>
              {fmt.ticket(p)}
            </Pill>
          ))}
        </ChoiceRow>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ChoiceRow label={t.sortBy}>
            {sorts.map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={sort === s.id}
                onClick={() => setSort(s.id)}
                className={
                  "min-h-11 shrink-0 cursor-pointer rounded-lg border px-4 text-[15px] whitespace-nowrap " +
                  (sort === s.id
                    ? "border-brand bg-brand-soft font-semibold text-link"
                    : "border-control bg-card font-medium text-ink hover:border-ink")
                }
              >
                {s.label}
              </button>
            ))}
          </ChoiceRow>
          <p className="num m-0 text-sm text-muted" aria-live="polite">
            {fill(t.summary, { n: rows.length, total: tickets.length })}
          </p>
        </div>
      </section>

      <Table minWidth="min-w-[1000px]">
        <thead>
          <HeadRow>
            <Th className="w-10 pl-5">{dict.table.rank}</Th>
            <Th left>{dict.table.game}</Th>
            <Th>{dict.table.ticket}</Th>
            <Th>{t.returnPerEuro}</Th>
            <Th>{t.chance}</Th>
            <Th>{t.sold}</Th>
            <Th>{t.since}</Th>
            <Th className="pr-5">{t.ends}</Th>
          </HeadRow>
        </thead>
        <tbody>
          {rows.map((x, i) => {
            const drop = x.paper - x.adjusted;
            return (
              <tr key={`${x.gameId}-${x.price}`} className="num text-right">
                <Td className="pl-5 text-muted">{i + 1}</Td>
                <Td left>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/${locale}/games/${x.gameId}/${x.price}`}
                      className="font-semibold text-ink no-underline hover:underline"
                    >
                      {x.name}
                    </Link>
                    {x.lowConfidence && <Chip tone="quiet">{t.lowData}</Chip>}
                  </div>
                </Td>
                <Td>{fmt.ticket(x.price)}</Td>
                <Td>
                  <div className="flex flex-col items-end gap-0.5">
                    <span className="font-semibold">{fmt.perEuro(x.adjusted)}</span>
                    {drop >= CLAIMED_DROP && (
                      <span className="text-xs font-semibold text-warn">{fill(t.delta, { value: fmt.perEuro(drop) })}</span>
                    )}
                  </div>
                </Td>
                <Td className="text-muted">{x.winChance ? fill(t.odds, { n: fmt.oneIn(x.winChance) }) : "—"}</Td>
                <Td className="text-muted">{x.soldShare === null ? "—" : fmt.pct(x.soldShare)}</Td>
                <Td className="text-muted">{x.onSaleSince ? fmt.date(x.onSaleSince) : "—"}</Td>
                <Td className="pr-5">
                  {x.saleEnd ? (
                    <span className="font-semibold text-warn">{fmt.date(x.saleEnd)}</span>
                  ) : x.lastDays ? (
                    <Chip tone="warn">{dict.chips.lastDays}</Chip>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </>
  );
}

function Pill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={
        "min-h-11 shrink-0 cursor-pointer rounded-full border px-4 text-[15px] whitespace-nowrap " +
        (on ? "border-ink bg-ink font-semibold text-paper" : "border-control bg-card font-medium text-ink hover:border-ink")
      }
    >
      {children}
    </button>
  );
}
