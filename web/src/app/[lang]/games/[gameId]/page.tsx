import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { isLocale } from "@/i18n/config";
import { getAllGameIds, getGame } from "@/lib/data";
import { GameView } from "./GameView";

// Every game known today is prerendered; a new one renders on its first visit.
export async function generateStaticParams() {
  return (await getAllGameIds()).map((gameId) => ({ gameId }));
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
