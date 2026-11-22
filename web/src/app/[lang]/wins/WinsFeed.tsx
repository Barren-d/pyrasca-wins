"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { HeadRow, Table, Td, Th } from "@/components/Table";
import type { Locale } from "@/i18n/config";
import type { Dictionary } from "@/i18n/dictionaries";
import type { FeedWin, WinFilter } from "@/lib/data";
import { fill, formatters } from "@/lib/format";

const BIG_PRIZE = 1000;

type Props = {
  locale: Locale;
  names: Record<string, string>;
  feeds: Record<WinFilter, { wins: FeedWin[]; total: number }>;
  dict: Pick<Dictionary, "wins" | "table">;
};

export function WinsFeed({ locale, names, feeds, dict }: Props) {
  const t = dict.wins;
  const [filter, setFilter] = useState<WinFilter>("x5"); // small wins are most of them
  const fmt = useMemo(() => formatters(locale), [locale]);
  const { wins, total } = feeds[filter];
  const filters: { id: WinFilter; label: string }[] = [
    { id: "all", label: t.filterAll },
    { id: "x5", label: t.filterX5 },
    { id: "k1", label: fill(t.filterAmount, { amount: fmt.prize(BIG_PRIZE) }) },
  ];

  return (
    <>
      <section className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label={t.show}
          className="-mx-6 flex flex-nowrap gap-2 overflow-x-auto px-6 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0"
        >
          {filters.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={
                "min-h-11 shrink-0 cursor-pointer rounded-full border px-[18px] text-[15px] whitespace-nowrap " +
                (filter === f.id ? "border-ink bg-ink font-semibold text-paper" : "border-control bg-card font-medium text-ink hover:border-ink")
              }
            >
              {f.label}
            </button>
          ))}
        </div>
        <p className="num m-0 text-sm text-muted" aria-live="polite">
          {fill(t.summary, { n: fmt.int(wins.length), total: fmt.int(total) })}
        </p>
      </section>

      {wins.length === 0 ? (
        <p className="m-0 text-[15px] text-muted">{t.empty}</p>
      ) : (
        <Table>
          <thead>
            <HeadRow>
              <Th left className="pl-5">
                {dict.table.game}
              </Th>
              <Th>{dict.table.ticket}</Th>
              <Th>{t.prize}</Th>
              <Th>{t.multiple}</Th>
              <Th left>{t.winner}</Th>
              <Th className="pr-5">{t.claimed}</Th>
            </HeadRow>
          </thead>
          <tbody>
            {wins.map((w) => {
              const name = (w.gameId && names[w.gameId]) || w.gameName;
              const href = w.gameId ? `/${locale}/games/${w.gameId}${w.ticketPrice === null ? "" : `/${w.ticketPrice}`}` : null;
              return (
                <tr key={w.claimId} className="num text-right">
                  <Td left className="pl-5">
                    {href ? (
                      <Link href={href} className="font-semibold text-ink no-underline hover:underline">
                        {name}
                      </Link>
                    ) : (
                      <span className="font-semibold">{name}</span>
                    )}
                  </Td>
                  <Td>{w.ticketPrice === null ? "—" : fmt.ticket(w.ticketPrice)}</Td>
                  <Td className={w.prize >= BIG_PRIZE ? "font-bold text-link" : "font-semibold"}>{fmt.prize(w.prize)}</Td>
                  <Td className="text-muted">{w.ticketPrice === null ? "—" : `${fmt.int(Math.round(w.prize / w.ticketPrice))}×`}</Td>
                  <Td left className="text-muted">
                    {w.winner ?? "—"}
                  </Td>
                  <Td className="pr-5 text-muted">{fmt.claimTime(w.claimedAt)}</Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </>
  );
}
