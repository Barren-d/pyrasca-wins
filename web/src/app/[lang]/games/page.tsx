import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import { isLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getTicketsOnSale } from "@/lib/data";
import { AllGamesTable } from "./AllGamesTable";

export async function generateMetadata({ params }: PageProps<"/[lang]/games">): Promise<Metadata> {
  const { lang } = await params;
  if (!isLocale(lang)) return {};
  return { title: (await getDictionary(lang)).allGames.title };
}

export default async function AllGames({ params }: PageProps<"/[lang]/games">) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();
  const [dict, tickets] = await Promise.all([getDictionary(lang), getTicketsOnSale()]);

  return (
    <>
      <SiteHeader locale={lang} dict={dict} active="all" />
      <main className="mx-auto flex max-w-[1120px] flex-col gap-7 px-6 pt-12 pb-[72px]">
        <section className="flex max-w-[760px] flex-col gap-3">
          <h1 className="m-0 font-display text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] sm:text-5xl">
            {dict.allGames.title}
          </h1>
          <p className="m-0 text-[17px] leading-[1.55] text-muted">{dict.allGames.intro}</p>
        </section>
        <AllGamesTable locale={lang} tickets={tickets} dict={{ allGames: dict.allGames, table: dict.table, chips: dict.chips }} />
        <p className="m-0 text-sm leading-normal text-muted">{dict.allGames.note}</p>
      </main>
      <SiteFooter dict={dict} />
    </>
  );
}
