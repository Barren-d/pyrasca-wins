import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { isLocale } from "@/i18n/config";
import { getGame, getPrerenderTickets } from "@/lib/data";
import { GameView } from "./GameView";

// Lists link to /games/[id]/[price], which is prebuilt; this plain address (used by
// "Relaunched" links) builds on its first visit. One id is needed for build validation.
export async function generateStaticParams() {
  return (await getPrerenderTickets()).slice(0, 1).map((t) => ({ gameId: t.gameId }));
}

export async function generateMetadata({ params }: PageProps<"/[lang]/games/[gameId]">): Promise<Metadata> {
  const { gameId } = await params;
  const game = (await getGame(gameId))[0];
  return game ? { title: game.name } : {};
}

/** A game at its highest ticket price. */
export default function GamePage({ params }: PageProps<"/[lang]/games/[gameId]">) {
  return (
    <Suspense fallback={<div className="min-h-screen" />}>
      <Game params={params} />
    </Suspense>
  );
}

async function Game({ params }: { params: PageProps<"/[lang]/games/[gameId]">["params"] }) {
  const { lang, gameId } = await params;
  if (!isLocale(lang)) notFound();
  return <GameView locale={lang} gameId={gameId} price={null} />;
}
