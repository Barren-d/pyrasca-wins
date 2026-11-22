import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { isLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getGameNames, getRecentWins } from "@/lib/data";
import { WinsFeed } from "./WinsFeed";

export async function generateMetadata({ params }: PageProps<"/[lang]/wins">): Promise<Metadata> {
  const { lang } = await params;
  if (!isLocale(lang)) return {};
  return { title: (await getDictionary(lang)).wins.title };
}

export default async function RecentWins({ params }: PageProps<"/[lang]/wins">) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();
  // All three filters are fetched up front, so switching between them is instant
  const [dict, names, all, x5, k1] = await Promise.all([
    getDictionary(lang),
    getGameNames(),
    getRecentWins("all"),
    getRecentWins("x5"),
    getRecentWins("k1"),
  ]);

  return (
    <>
      <SiteHeader locale={lang} dict={dict} active="wins" />
      <main className="mx-auto flex max-w-[1120px] flex-col gap-7 px-6 pt-12 pb-[72px]">
        <section className="flex max-w-[760px] flex-col gap-3">
          <h1 className="m-0 font-display text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] sm:text-5xl">{dict.wins.title}</h1>
          <p className="m-0 text-[17px] leading-[1.55] text-muted">{dict.wins.intro}</p>
        </section>
        <WinsFeed locale={lang} names={names} feeds={{ all, x5, k1 }} dict={{ wins: dict.wins, table: dict.table }} />
        <p className="m-0 text-sm leading-normal text-muted">{dict.wins.note}</p>
      </main>
      <SiteFooter dict={dict} />
    </>
  );
}
