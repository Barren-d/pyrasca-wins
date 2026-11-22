import { NextResponse, type NextRequest } from "next/server";
import { defaultLocale, isLocale, LOCALE_COOKIE, locales, type Locale } from "@/i18n/config";

/** Language for a visitor: the one they chose before, else their browser's first match. */
function pickLocale(request: NextRequest): Locale {
  const saved = request.cookies.get(LOCALE_COOKIE)?.value;
  if (saved && isLocale(saved)) return saved;
  const accepted = (request.headers.get("accept-language") ?? "")
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { lang: tag.toLowerCase().split("-")[0], q: q ? Number(q) : 1 };
    })
    .sort((a, b) => b.q - a.q);
  return (accepted.find((a) => isLocale(a.lang))?.lang as Locale) ?? defaultLocale;
}

/**
 * Every page lives under /ca, /en or /es. Other paths go to the visitor's language;
 * a visit to a language's pages remembers it for next time.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const current = locales.find((l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`));
  if (current) {
    if (request.cookies.get(LOCALE_COOKIE)?.value === current) return;
    const response = NextResponse.next();
    response.cookies.set(LOCALE_COOKIE, current, { path: "/", maxAge: 31_536_000, sameSite: "lax" });
    return response;
  }
  request.nextUrl.pathname = `/${pickLocale(request)}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(request.nextUrl);
}

export const config = {
  // Skip Next.js internals and files with an extension (favicon.ico, images, …)
  matcher: ["/((?!_next|.*\\..*).*)"],
};
