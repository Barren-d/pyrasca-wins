import Link from "next/link";
import type { Locale } from "@/i18n/config";
import type { Dictionary } from "@/i18n/dictionaries";
import { LanguageMenu } from "./LanguageMenu";
import { ThemeToggle } from "./ThemeToggle";

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
      {/* Phone: logo and language on top, the links in one sideways-scrolling row below.
          From md up: logo left, links and language together on the right. */}
      <nav className="mx-auto flex min-h-16 max-w-[1120px] flex-wrap items-center gap-x-3 px-4 md:px-6">
        <Link href={`/${locale}`} className="py-3 font-display text-[22px] font-bold tracking-[-0.02em] text-ink no-underline">
          py<span className="text-logo">Rasca</span>
        </Link>
        <div className="order-last -mx-4 flex w-[calc(100%+2rem)] flex-nowrap gap-1 overflow-x-auto px-1 [scrollbar-width:none] md:order-none md:mx-0 md:ml-auto md:w-auto md:px-0">
          {links.map((l) => (
            <Link
              key={l.id}
              href={l.href}
              aria-current={l.id === active ? "page" : undefined}
              className={
                "shrink-0 px-3 py-3 text-[15px] whitespace-nowrap no-underline md:px-3.5 " +
                (l.id === active ? "border-b-2 border-brand font-semibold text-ink" : "font-medium text-muted hover:text-ink")
              }
            >
              {l.label}
            </Link>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2 md:ml-0">
          <ThemeToggle toDark={dict.nav.darkMode} toLight={dict.nav.lightMode} />
          <LanguageMenu current={locale} label={dict.nav.language} />
        </div>
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
