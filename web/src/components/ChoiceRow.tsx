/**
 * A labelled row of filter or sort buttons. On phones the label sits above and the
 * buttons stay on one line that scrolls sideways; from sm up they sit inline and wrap.
 * Buttons inside should be `shrink-0`.
 */
export function ChoiceRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <span className="text-sm font-semibold text-muted sm:min-w-[88px]">{label}</span>
      <div
        role="group"
        aria-label={label}
        className="-mx-6 flex flex-nowrap gap-2 overflow-x-auto px-6 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0"
      >
        {children}
      </div>
    </div>
  );
}
