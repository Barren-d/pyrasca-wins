"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { localeNames, locales, type Locale } from "@/i18n/config";
import { Flag } from "./Flag";

/** Round flag button in the header; opens a menu of the three languages. */
export function LanguageMenu({ current, label }: { current: Locale; label: string }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const root = useRef<HTMLDivElement>(null);

  // Close on outside click or Escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Same page in another language: swap the first path segment
  const hrefFor = (locale: Locale) => {
    const rest = pathname.split("/").slice(2).join("/");
    return `/${locale}${rest ? `/${rest}` : ""}`;
  };

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${label}: ${localeNames[current]}`}
        title={localeNames[current]}
        className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-full border border-line bg-card"
      >
        <Flag locale={current} size={30} />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={label}
          className="absolute right-0 top-[52px] z-20 min-w-[190px] rounded-xl border border-line bg-card p-1.5 shadow-[0_12px_32px_rgba(21,23,28,0.12)]"
        >
          {locales.map((locale) => (
            <Link
              key={locale}
              href={hrefFor(locale)}
              role="menuitemradio"
              aria-checked={locale === current}
              hrefLang={locale}
              onClick={() => setOpen(false)}
              className="flex min-h-11 items-center gap-3 rounded-lg px-3.5 text-[15px] text-ink no-underline hover:bg-paper"
            >
              <Flag locale={locale} size={22} />
              <span className="flex-1">{localeNames[locale]}</span>
              {locale === current && (
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0A6A4E" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
