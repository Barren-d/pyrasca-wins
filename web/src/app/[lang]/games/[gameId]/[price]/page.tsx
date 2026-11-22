import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { isLocale } from "@/i18n/config";
import { getAllGameIds, getGame } from "@/lib/data";
import { formatters } from "@/lib/format";
import { GameView } from "../GameView";

export async function generateStaticParams() {
  const ids = await getAllGameIds();
  const games = await Promise.all(ids.map(getGame));
  return games.flatMap((prices) => prices.map((p) => ({ gameId: p.gameId, price: String(p.price) })));
}

export async function generateMetadata({ params }: PageProps<"/[lang]/games/[gameId]/[price]">): Promise<Metadata> {
  const { lang, gameId, price } = await params;
  const game = (await getGame(gameId)).find((p) => p.price === Number(price));
  if (!game || !isLocale(lang)) return {};
  return { title: `${game.name} ${formatters(lang).ticket(game.price)}` };
}

/** A game at one ticket price, e.g. /es/games/EJ4/5 */
export default function GamePricePage({ params }: PageProps<"/[lang]/games/[gameId]/[price]">) {
  return (
    <Suspense fallback={<div className="min-h-screen" />}>
      <GamePrice params={params} />
    </Suspense>
  );
}

async function GamePrice({ params }: { params: PageProps<"/[lang]/games/[gameId]/[price]">["params"] }) {
  const { lang, gameId, price } = await params;
  const value = Number(price);
  if (!isLocale(lang) || !Number.isFinite(value)) notFound();
  return <GameView locale={lang} gameId={gameId} price={value} />;
}
