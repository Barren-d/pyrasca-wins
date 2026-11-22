import Link from "next/link";
import type { Locale } from "@/i18n/config";
import type { Dictionary } from "@/i18n/dictionaries";
import { LanguageMenu } from "./LanguageMenu";

export type Section = "picks" | "all" | "wins" | "archive";

export function SiteHeader({ locale, dict, active }: { locale: Locale; dict: Dictionary; active: Section }) {
  const links: { id: Section; href: string; label: string }[] = [
    { id: "picks", href: `/${locale}`, label: dict.nav.picks },
    { id: "all", href: `/${locale}/games`, label: dict.nav.all },
    { id: "wins", href: `/${locale}/wins`, label: dict.nav.wins },
    { id: "archive", href: `/${locale}/archive`, label: dict.nav.archive },
  ];
  return (
    <header className="border-b border-line bg-card">
      <nav className="mx-auto flex min-h-16 max-w-[1120px] flex-wrap items-center justify-between gap-3 px-6">
        <Link href={`/${locale}`} className="font-display text-[22px] font-bold tracking-[-0.02em] text-ink no-underline">
          py<span className="text-brand">Rasca</span>
        </Link>
        <div className="ml-auto flex flex-wrap gap-1">
          {links.map((l) => (
            <Link
              key={l.id}
              href={l.href}
              aria-current={l.id === active ? "page" : undefined}
              className={
                "px-3.5 py-3 text-[15px] no-underline " +
                (l.id === active ? "border-b-2 border-brand font-semibold text-ink" : "font-medium text-muted hover:text-ink")
              }
            >
              {l.label}
            </Link>
          ))}
        </div>
        <LanguageMenu current={locale} label={dict.nav.language} />
      </nav>
    </header>
  );
}

export function SiteFooter({ dict }: { dict: Dictionary }) {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-[1120px] flex-wrap justify-between gap-3 p-6 text-sm text-muted">
        <span>{dict.footer.disclaimer}</span>
        <span>{dict.footer.responsible}</span>
      </div>
    </footer>
  );
}
