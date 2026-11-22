import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { isLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getBiggestWinsThisWeek, getClaimCount, getLastUpdate, getTicketsOnSale } from "@/lib/data";
import { fill, formatters } from "@/lib/format";
import { Picks } from "./Picks";

export default async function Home({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();
  const dict = await getDictionary(lang);
  const fmt = formatters(lang);

  const [tickets, claims, updated, wins] = await Promise.all([
    getTicketsOnSale(),
    getClaimCount(),
    getLastUpdate(),
    getBiggestWinsThisWeek(),
  ]);
  const gamesOnSale = new Set(tickets.map((t) => t.gameId)).size;
  const best = tickets[0]?.adjusted;
  // The winners list sometimes shortens names ("Isla Pirata"); show the game's own name
  const nameOf = new Map(tickets.map((t) => [t.gameId, t.name]));

  return (
    <>
      <SiteHeader locale={lang} dict={dict} active="picks" />
      <main className="mx-auto flex max-w-[1120px] flex-col gap-12 px-6 pt-14 pb-[72px]">
        <section className="flex max-w-[760px] flex-col gap-4">
          {updated && (
            <p className="m-0 text-sm font-semibold uppercase tracking-[0.08em] text-brand">
              {fill(dict.home.updated, { time: fmt.updated(updated) })}
            </p>
          )}
          <h1 className="m-0 font-display text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] sm:text-[52px]">
            {dict.home.title}
          </h1>
          <p className="m-0 text-lg leading-[1.55] text-muted">{dict.home.intro}</p>
        </section>

        <section aria-label="Key figures" className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
          <Stat label={dict.home.gamesOnSale} value={fmt.int(gamesOnSale)} />
          <Stat label={dict.home.winsTracked} value={fmt.int(claims)} />
          <Stat
            label={dict.home.bestReturn}
            value={best === undefined ? "—" : fmt.perEuro(best)}
            unit={best === undefined ? undefined : dict.home.perEuro}
          />
        </section>

        <Picks locale={lang} tickets={tickets} dict={{ home: dict.home, table: dict.table, chips: dict.chips }} />

        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="m-0 font-display text-[28px] font-semibold tracking-[-0.02em]">{dict.home.biggestWins}</h2>
            <Link href={`/${lang}/wins`} className="text-[15px] font-semibold text-brand hover:text-brand-dark">
              {dict.home.allWins}
            </Link>
          </div>
          {wins.length === 0 ? (
            <p className="m-0 text-[15px] text-muted">{dict.home.noWins}</p>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
              {wins.map((w) => (
                <div key={w.claimId} className="flex flex-col gap-2 rounded-xl border border-line bg-card px-6 py-5">
                  <span className="num font-display text-[32px] font-semibold tracking-[-0.02em]">{fmt.prize(w.prize)}</span>
                  <span className="text-[15px] font-semibold">{(w.gameId && nameOf.get(w.gameId)) || w.gameName}</span>
                  <span className="num text-sm text-muted">
                    {w.ticketPrice === null
                      ? fmt.dayMonth(w.claimedAt)
                      : fill(dict.home.winMeta, { price: fmt.ticket(w.ticketPrice), date: fmt.dayMonth(w.claimedAt) })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
      <SiteFooter dict={dict} />
    </>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-line bg-card px-6 py-5">
      <span className="text-sm text-muted">{label}</span>
      <span className="num font-display text-4xl font-semibold">
        {value} {unit && <span className="text-base font-medium text-muted">{unit}</span>}
      </span>
    </div>
  );
}
