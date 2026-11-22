import type { ReactNode } from "react";

export function Table({ children, minWidth = "min-w-[720px]" }: { children: ReactNode; minWidth?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-card">
      <table className={`w-full border-collapse text-[15px] ${minWidth}`}>{children}</table>
    </div>
  );
}

export function HeadRow({ children }: { children: ReactNode }) {
  return <tr className="text-right text-[13px] text-muted">{children}</tr>;
}

export function Th({ children, left, className = "" }: { children: ReactNode; left?: boolean; className?: string }) {
  return (
    <th className={`border-b border-line px-3 py-3.5 font-semibold ${left ? "text-left" : ""} ${className}`}>{children}</th>
  );
}

export function Td({ children, left, className = "" }: { children: ReactNode; left?: boolean; className?: string }) {
  // Right-aligned cells hold numbers and dates: keep them on one line
  return <td className={`border-b border-line-soft px-3 py-3.5 ${left ? "text-left" : "whitespace-nowrap"} ${className}`}>{children}</td>;
}

export function Chip({ children, tone }: { children: ReactNode; tone: "warn" | "neutral" | "strong" | "quiet" }) {
  const styles = {
    warn: "bg-warn-soft text-warn font-semibold",
    neutral: "bg-chip text-chip-ink font-semibold",
    strong: "bg-warn text-card font-bold",
    quiet: "bg-line-soft text-muted font-semibold",
  }[tone];
  return <span className={`rounded-full px-2 py-[3px] text-xs whitespace-nowrap ${styles}`}>{children}</span>;
}
