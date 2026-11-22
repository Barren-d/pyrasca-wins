import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { HeadRow, Table, Td, Th } from "@/components/Table";
import { isLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getInactiveTickets, sameName } from "@/lib/data";
import { fill, formatters } from "@/lib/format";

export async function generateMetadata({ params }: PageProps<"/[lang]/archive">): Promise<Metadata> {
  const { lang } = await params;
  if (!isLocale(lang)) return {};
  return { title: (await getDictionary(lang)).archive.title };
}

const DAY = 86_400_000;

export default async function Archive({ params }: PageProps<"/[lang]/archive">) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();
  const [dict, tickets] = await Promise.all([getDictionary(lang), getInactiveTickets()]);
  const t = dict.archive;
  const fmt = formatters(lang);

  const lifeDays = (x: (typeof tickets)[number]) => (x.launched ? Math.round((Date.parse(x.ended) - Date.parse(x.launched)) / DAY) : null);
  const life = (days: number) =>
    days < 60 ? fill(t.weeks, { n: Math.max(1, Math.round(days / 7)) }) : fill(t.months, { n: Math.round(days / 30.4) });

  // Figures count games, not ticket prices
  const games = [...new Map(tickets.map((x) => [x.gameId, x])).values()];
  const lives = games.map(lifeDays).filter((d): d is number => d !== null);
  const typical = median(lives);
  const withTop = games.filter((x) => x.topPrinted !== null);
  const noTopClaim = withTop.filter((x) => !x.topClaimed).length;

  return (
    <>
      <SiteHeader locale={lang} dict={dict} active="archive" />
      <main className="mx-auto flex max-w-[1120px] flex-col gap-7 px-6 pt-12 pb-[72px]">
        <section className="flex max-w-[760px] flex-col gap-3">
          <h1 className="m-0 font-display text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] sm:text-5xl">{t.title}</h1>
          <p className="m-0 text-[17px] leading-[1.55] text-muted">{t.intro}</p>
        </section>

        <section aria-label="Key figures" className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
          <Stat label={t.count} value={fmt.int(games.length)} />
          <Stat label={t.typicalLife} value={typical === null ? "—" : life(typical)} />
          <Stat label={t.noTopClaim} value={fmt.int(noTopClaim)} unit={fill(t.ofN, { n: fmt.int(withTop.length) })} />
        </section>

        <Table minWidth="min-w-[960px]">
          <thead>
            <HeadRow>
              <Th left className="pl-5">
                {dict.table.game}
              </Th>
              <Th>{dict.table.ticket}</Th>
              <Th>{t.ended}</Th>
              <Th>{t.onSaleFor}</Th>
              <Th>{dict.allGames.returnPerEuro}</Th>
              <Th>{t.topPrize}</Th>
              <Th className="pr-5">{t.topClaims}</Th>
            </HeadRow>
          </thead>
          <tbody>
            {tickets.map((x) => {
              const days = lifeDays(x);
              return (
                <tr key={`${x.gameId}-${x.price}`} className="num text-right">
                  <Td left className="pl-5">
                    <div className="flex flex-col gap-1">
                      <Link href={`/${lang}/games/${x.gameId}/${x.price}`} className="font-semibold text-ink no-underline hover:underline">
                        {x.name}
                      </Link>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                        <span>{fill(t.code, { code: x.gameId })}</span>
                        {x.relaunch && (
                          <Link
                            href={`/${lang}/games/${x.relaunch.gameId}`}
                            className="rounded-full bg-[#E3F1EC] px-2 py-0.5 font-semibold text-brand-dark no-underline hover:underline"
                          >
                            {sameName(x.relaunch.name, x.name)
                              ? fill(t.relaunched, { date: x.relaunch.since ? fmt.date(x.relaunch.since) : "" }).trim()
                              : fill(t.relaunchedAs, { name: x.relaunch.name })}
                          </Link>
                        )}
                      </div>
                    </div>
                  </Td>
                  <Td>{fmt.ticket(x.price)}</Td>
                  <Td className="text-muted">{fmt.date(x.ended)}</Td>
                  <Td className="text-muted">{days === null ? "—" : life(days)}</Td>
                  <Td className="font-semibold">{x.paper === null ? "—" : fmt.perEuro(x.paper)}</Td>
                  <Td>{x.topPrize === null ? "—" : fmt.prize(x.topPrize)}</Td>
                  <Td className={`pr-5 ${x.topClaimed ? "font-semibold text-warn" : "text-muted"}`}>
                    {x.topPrinted === null ? "—" : fill(t.claimsOf, { claimed: fmt.int(x.topClaimed ?? 0), printed: fmt.int(x.topPrinted) })}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>

        <p className="m-0 text-sm leading-normal text-muted">{t.note}</p>
      </main>
      <SiteFooter dict={dict} />
    </>
  );
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
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
