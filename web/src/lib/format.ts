import { intlLocale, type Locale } from "@/i18n/config";

/** Fill "{name}" placeholders in a translated string. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`));
}

/** Locale-aware formatters. Safe on server and client (no server-only imports). */
export function formatters(locale: Locale) {
  const tag = intlLocale[locale];
  const euro = (digits: number) =>
    new Intl.NumberFormat(tag, {
      style: "currency",
      currency: "EUR",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  const euro0 = euro(0);
  const euro2 = euro(2);
  const euro3 = euro(3);
  const int = new Intl.NumberFormat(tag);
  const pct1 = new Intl.NumberFormat(tag, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
  // Official dates are calendar days; claim times are stored as Spanish local time
  // in a UTC field, so both are formatted in UTC to show them as published.
  const dayMonth = new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", timeZone: "UTC" });
  const date = new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const dec1 = new Intl.NumberFormat(tag, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const claimTime = new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  const updated = new Intl.DateTimeFormat(tag, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Madrid", // always Spanish time, like the draw and claim times
  });

  return {
    /** Ticket price: €10, €2, €0.50, €0.25 */
    ticket: (n: number) => (Number.isInteger(n) ? euro0 : euro2).format(n),
    /** Return per €1, three decimals: €0.740 */
    perEuro: (n: number) => euro3.format(n),
    /** Prize amount: €85,000 */
    prize: (n: number) => (Number.isInteger(n) ? euro0 : euro2).format(n),
    int: (n: number) => int.format(n),
    pct: (share: number) => pct1.format(share),
    /** Odds denominator: a 36.7% chance → "2.7" (as in "1 in 2.7") */
    oneIn: (share: number) => dec1.format(1 / share),
    dayMonth: (iso: string) => dayMonth.format(new Date(iso)),
    date: (iso: string) => date.format(new Date(iso)),
    /** Claim time as published in the winners list: "21 Nov, 17:10" */
    claimTime: (iso: string) => claimTime.format(new Date(iso)),
    updated: (iso: string) => updated.format(new Date(iso)),
  };
}
