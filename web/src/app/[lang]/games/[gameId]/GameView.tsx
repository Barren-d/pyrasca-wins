import Link from "next/link";
import { notFound } from "next/navigation";
import { BackLink } from "@/components/BackLink";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { HeadRow, Table, Td, Th } from "@/components/Table";
import type { Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getGame, getGameClaims, getHistory, getPrizeTable, getTicketsOnSale } from "@/lib/data";
import { fill, formatters } from "@/lib/format";
import { HistoryChart } from "./HistoryChart";

const CLAIMED_DROP = 0.005; // big prizes gone: the drop is worth flagging
const VISIBLE_DROP = 0.0005; // anything that shows at three decimals

/** The game page for one ticket price. `price` null = the game's highest price. */
export async function GameView({ locale, gameId, price }: { locale: Locale; gameId: string; price: number | null }) {
  const [dict, prices] = await Promise.all([getDictionary(locale), getGame(gameId)]);
  const g = price === null ? prices[0] : prices.find((p) => p.price === price);
  if (!g) notFound();
  const multiPrice = prices.length > 1;
  const [tiers, history, claims, onSale] = await Promise.all([
    getPrizeTable(gameId, g.price),
    getHistory(gameId, g.price),
    getGameClaims(gameId, g.price, multiPrice),
    g.active ? getTicketsOnSale() : Promise.resolve([]),
  ]);
  const t = dict.game;
  const fmt = formatters(locale);
  const rank = onSale.findIndex((x) => x.gameId === gameId && x.price === g.price) + 1;
  const drop = g.paper - g.adjusted;
  const oddsOf = (printed: number) => {
    if (!g.seriesSize || !printed) return "—";
    const n = g.seriesSize / printed;
    return fill(dict.allGames.odds, { n: n < 10 ? fmt.oneIn(1 / n) : fmt.int(Math.round(n)) });
  };

  const facts = [
    fill(t.ticketLine, { price: fmt.ticket(g.price) }),
    g.onSaleSince && fill(t.onSaleSince, { date: fmt.date(g.onSaleSince) }),
    g.seriesSize && fill(t.series, { n: fmt.int(g.seriesSize) }),
  ].filter(Boolean);

  return (
    <>
      <SiteHeader locale={locale} dict={dict} active={g.active ? "all" : "archive"} />
      <main className="mx-auto flex max-w-[1120px] flex-col gap-10 px-6 pt-8 pb-[72px]">
        <section className="flex flex-col gap-5">
          <BackLink
            fallback={g.active ? `/${locale}/games` : `/${locale}/archive`}
            className="flex w-fit items-center gap-1.5 text-[15px] font-semibold text-brand no-underline hover:text-brand-dark"
          >
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            {t.back}
          </BackLink>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-col gap-2">
              <h1 className={`m-0 font-display text-[44px] leading-none font-semibold tracking-[-0.03em] sm:text-[56px] ${g.active ? "" : "text-chip-ink"}`}>
                {g.name}
              </h1>
              <p className="num m-0 text-base text-muted">{facts.join(" · ")}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {!g.active && (
                <span className="rounded-full bg-chip px-3 py-1.5 text-sm font-semibold text-chip-ink">
                  {t.inactive}
                  {g.lastSeen && ` · ${fill(t.lastSeenOn, { date: fmt.date(g.lastSeen) })}`}
                </span>
              )}
              {g.saleEnd && (
                <a href={g.endSourceUrl ?? undefined} className="rounded-full bg-warn-soft px-3 py-1.5 text-sm font-semibold text-warn no-underline">
                  {fill(dict.chips.ends, { date: fmt.date(g.saleEnd) })}
                </a>
              )}
              {!g.saleEnd && g.lastDays && g.active && (
                <span className="rounded-full bg-warn-soft px-3 py-1.5 text-sm font-semibold text-warn">{dict.chips.lastDays}</span>
              )}
              {rank > 0 && (
                <span className="num rounded-full bg-[#E3F1EC] px-3 py-1.5 text-sm font-semibold text-brand-dark">
                  {fill(t.rank, { n: rank, total: onSale.length })}
                </span>
              )}
            </div>
          </div>
          {multiPrice && (
            <div role="group" aria-label={t.priceTabs} className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-muted">{t.priceTabs}</span>
              {prices.map((p) => (
                <Link
                  key={p.price}
                  href={`/${locale}/games/${gameId}/${p.price}`}
                  replace // switching price doesn't add a step for Back
                  scroll={false}
                  aria-current={p.price === g.price ? "page" : undefined}
                  className={
                    "num flex min-h-10 items-center rounded-full border px-4 text-[15px] no-underline " +
                    (p.price === g.price ? "border-ink bg-ink font-semibold text-white" : "border-control bg-card font-medium text-ink hover:border-ink")
                  }
                >
                  {fmt.ticket(p.price)}
                </Link>
              ))}
            </div>
          )}
        </section>

        <section aria-label="Key figures" className="grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-4">
          <Figure
            label={t.expectedReturn}
            value={fmt.perEuro(g.adjusted)}
            unit={t.perEuro}
            note={`${fill(t.backPerTicket, { back: fmt.prize(Math.round(g.adjusted * g.price * 100) / 100), price: fmt.ticket(g.price) })} · ${
              drop >= VISIBLE_DROP ? fill(t.belowPaper, { value: fmt.perEuro(drop) }) : t.samePaper
            }`}
            warn={drop >= CLAIMED_DROP}
          />
          <Figure
            label={t.chanceAny}
            value={g.winChance ? fill(dict.allGames.odds, { n: fmt.oneIn(g.winChance) }) : "—"}
            note={g.winningTickets ? fill(t.winningTickets, { n: fmt.int(g.winningTickets) }) : ""}
          />
          <Figure
            label={t.sold}
            value={g.soldShare === null ? "—" : fmt.pct(g.soldShare)}
            note={g.lowConfidence ? t.soldNoteLow : t.soldNote}
          />
          <Figure
            label={t.topPrize}
            value={g.topPrize === null ? "—" : fmt.prize(g.topPrize)}
            note={
              g.topPrizesPrinted === null
                ? ""
                : `${fill(t.topPrinted, { printed: fmt.int(g.topPrizesPrinted) })}, ${
                    g.topPrizesClaimed ? fill(t.topClaimed, { claimed: fmt.int(g.topPrizesClaimed) }) : t.topNoneClaimed
                  }`
            }
            warn={!!g.topPrizesClaimed}
          />
        </section>

        <section className="flex flex-col gap-4 rounded-xl border border-line bg-card px-6 py-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="m-0 font-display text-[22px] font-semibold tracking-[-0.02em]">{t.historyTitle}</h2>
            {history.length > 0 && (
              <span className="num text-sm text-muted">
                {fill(t.tracked, { from: fmt.date(history[0].at), to: fmt.date(history[history.length - 1].at) })}
              </span>
            )}
          </div>
          {history.length >= 2 ? (
            <HistoryChart
              locale={locale}
              points={history}
              paper={g.paper}
              labels={{ soldSeries: t.soldSeries, adjSeries: t.adjSeries, onPaper: t.onPaper, noData: t.noData }}
            />
          ) : (
            <p className="m-0 text-[15px] text-muted">{t.noHistory}</p>
          )}
          <p className="m-0 text-sm leading-normal text-muted">{t.historyNote}</p>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 font-display text-[28px] font-semibold tracking-[-0.02em]">{t.prizeTiers}</h2>
          <Table minWidth="min-w-[560px]">
            <thead>
              <HeadRow>
                <Th left className="pl-5">
                  {t.prize}
                </Th>
                <Th>{t.perSeries}</Th>
                <Th>{t.odds}</Th>
                <Th className="pr-5">{t.claimsSeen}</Th>
              </HeadRow>
            </thead>
            <tbody>
              {tiers.map((tier) => (
                <tr key={tier.prize} className="num text-right">
                  <Td left className="pl-5">
                    <span className="font-semibold">{fmt.prize(tier.prize)}</span>
                    {tier.annuityYears && tier.annuityPerYear && (
                      <span className="block text-xs text-muted">
                        {fill(t.annuity, { amount: fmt.prize(tier.annuityPerYear), years: tier.annuityYears })}
                      </span>
                    )}
                  </Td>
                  <Td>{fmt.int(tier.printed)}</Td>
                  <Td className="text-muted">{oddsOf(tier.printed)}</Td>
                  <Td className={`pr-5 ${tier.claimed >= tier.printed ? "font-semibold text-warn" : ""}`}>{fmt.int(tier.claimed)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </section>

        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="m-0 font-display text-[28px] font-semibold tracking-[-0.02em]">{fill(t.latestClaims, { name: g.name })}</h2>
            <Link href={`/${locale}/wins`} className="text-[15px] font-semibold text-brand hover:text-brand-dark">
              {dict.home.allWins}
            </Link>
          </div>
          {claims.length === 0 ? (
            <p className="m-0 text-[15px] text-muted">{t.noClaims}</p>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
              {claims.map((c) => (
                <div key={c.claimId} className="num flex flex-col gap-1 rounded-xl border border-line bg-card px-4 py-3.5">
                  <span className="font-display text-[22px] font-semibold">{fmt.prize(c.prize)}</span>
                  <span className="text-sm font-medium">{c.winner ?? "—"}</span>
                  <span className="text-[13px] text-muted">{fmt.claimTime(c.claimedAt)}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <p className="m-0 text-sm text-muted">
          <a href={g.url} className="font-semibold text-brand hover:text-brand-dark" rel="noopener">
            {t.officialPage}
          </a>
          {g.endSourceUrl && (
            <>
              {" · "}
              <a href={g.endSourceUrl} className="font-semibold text-brand hover:text-brand-dark" rel="noopener">
                {t.endNotice}
              </a>
            </>
          )}
        </p>
      </main>
      <SiteFooter dict={dict} />
    </>
  );
}

function Figure({ label, value, unit, note, warn }: { label: string; value: string; unit?: string; note: string; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-line bg-card px-6 py-5">
      <span className="text-sm text-muted">{label}</span>
      <span className="num font-display text-[28px] leading-tight font-semibold">
        {value} {unit && <span className="text-base font-medium text-muted">{unit}</span>}
      </span>
      {note && <span className={`num text-[13px] ${warn ? "font-semibold text-warn" : "text-muted"}`}>{note}</span>}
    </div>
  );
}
