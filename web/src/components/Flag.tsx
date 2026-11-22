import type { Locale } from "@/i18n/config";

/** Round flag for the language menu: Catalonia (senyera), UK, Spain. */
export function Flag({ locale, size }: { locale: Locale; size: number }) {
  return (
    <span
      className="block shrink-0 overflow-hidden rounded-full shadow-[0_0_0_1px_rgba(21,23,28,0.12)]"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {locale === "ca" && (
        <svg viewBox="0 0 27 27" width="100%" height="100%">
          <rect width="27" height="27" fill="#FCDD09" />
          {[3, 9, 15, 21].map((y) => (
            <rect key={y} y={y} width="27" height="3" fill="#DA121A" />
          ))}
        </svg>
      )}
      {locale === "es" && (
        <svg viewBox="0 0 30 30" width="100%" height="100%">
          <rect width="30" height="30" fill="#AA151B" />
          <rect y="7.5" width="30" height="15" fill="#F1BF00" />
        </svg>
      )}
      {locale === "en" && (
        <svg viewBox="15 0 30 30" width="100%" height="100%">
          <clipPath id={`uk-${size}`}>
            <path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
          </clipPath>
          <rect width="60" height="30" fill="#012169" />
          <path d="M0,0 L60,30 M60,0 L0,30" stroke="#FFFFFF" strokeWidth="6" />
          <path d="M0,0 L60,30 M60,0 L0,30" clipPath={`url(#uk-${size})`} stroke="#C8102E" strokeWidth="4" />
          <path d="M30,0 v30 M0,15 h60" stroke="#FFFFFF" strokeWidth="10" />
          <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" strokeWidth="6" />
        </svg>
      )}
    </span>
  );
}
