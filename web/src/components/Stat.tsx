/** Key figures: compact tiles side by side on phones, roomy cards from sm up. */
export function StatGrid({ children, label, cols = 3 }: { children: React.ReactNode; label: string; cols?: 2 | 3 }) {
  return (
    <section
      aria-label={label}
      className={`grid gap-2 sm:grid-cols-[repeat(auto-fit,minmax(230px,1fr))] sm:gap-4 ${cols === 3 ? "grid-cols-3" : "grid-cols-2"}`}
    >
      {children}
    </section>
  );
}

export function Stat({ label, value, unit, note, warn }: { label: string; value: string; unit?: string; note?: string; warn?: boolean }) {
  return (
    <div className="flex flex-col justify-between gap-1.5 rounded-xl border border-line bg-card px-3 py-3 sm:px-6 sm:py-5">
      <span className="text-xs leading-snug text-muted sm:text-sm">{label}</span>
      <div className="flex flex-col gap-1">
        <span className="num font-display text-xl leading-tight font-semibold sm:text-[32px]">
          {value} {unit && <span className="block text-xs font-medium text-muted sm:inline sm:text-base">{unit}</span>}
        </span>
        {note && <span className={`num text-xs sm:text-[13px] ${warn ? "font-semibold text-warn" : "text-muted"}`}>{note}</span>}
      </div>
    </div>
  );
}
