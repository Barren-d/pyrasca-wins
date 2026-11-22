export const locales = ["ca", "en", "es"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "es";
export const LOCALE_COOKIE = "NEXT_LOCALE";

export const isLocale = (value: string): value is Locale =>
  (locales as readonly string[]).includes(value);

/** BCP 47 tag used for number and date formatting. */
export const intlLocale: Record<Locale, string> = {
  ca: "ca-ES",
  en: "en-IE", // euro-area English: "€0.740", day-month dates
  es: "es-ES",
};

export const localeNames: Record<Locale, string> = {
  ca: "Català",
  en: "English",
  es: "Español",
};
