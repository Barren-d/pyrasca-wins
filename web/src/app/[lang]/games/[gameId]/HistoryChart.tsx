"use client";

import { useMemo, useRef, useState } from "react";
import type { Locale } from "@/i18n/config";
import type { HistoryPoint } from "@/lib/data";
import { fill, formatters } from "@/lib/format";

// Two thin panels on one shared date axis (never two y-scales on one plot):
// share of the series sold on top, adjusted return per €1 below.
const SOLD = "var(--color-chart-sold)";
const RETURN = "var(--color-chart-return)";
const PAPER = "var(--color-chart-paper)";
const GAP_DAYS = 10; // a longer gap between points is drawn as "no data"
const W = 1000; // viewBox width; the SVG stretches to its container
const H = 120; // viewBox height of each panel

type Labels = { soldSeries: string; adjSeries: string; onPaper: string; noData: string };

type Props = { locale: Locale; points: HistoryPoint[]; paper: number; labels: Labels };

type P = { t: number; sold: number | null; adjusted: number | null };

export function HistoryChart({ locale, points, paper, labels }: Props) {
  const fmt = useMemo(() => formatters(locale), [locale]);
  const monthFmt = useMemo(() => new Intl.DateTimeFormat(locale === "en" ? "en-IE" : `${locale}-ES`, { month: "short", timeZone: "Europe/Madrid" }), [locale]);
  const pts: P[] = useMemo(() => points.map((p) => ({ t: Date.parse(p.at), sold: p.sold, adjusted: p.adjusted })), [points]);
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const t0 = pts[0].t;
  const t1 = pts[pts.length - 1].t;
  const x = (t: number) => (t1 === t0 ? W / 2 : ((t - t0) / (t1 - t0)) * W);
  const xPct = (t: number) => (x(t) / W) * 100;

  // Runs of points without a long gap, and the gaps between them
  const runs: P[][] = [];
  const gaps: [number, number][] = [];
  pts.forEach((p, i) => {
    if (i > 0 && p.t - pts[i - 1].t > GAP_DAYS * 86_400_000) {
      gaps.push([pts[i - 1].t, p.t]);
      runs.push([]);
    }
    if (runs.length === 0) runs.push([]);
    runs[runs.length - 1].push(p);
  });

  // Scales
  // Early estimates from few claims can be wildly high (even over 100%). Scale the axis
  // to the typical values and pin anything far above them to the top edge; the hover
  // still shows the real value. Round steps (1, 2 or 5 × a power of ten) for the ticks.
  const soldValues = pts.map((p) => p.sold).filter((v): v is number => v !== null);
  const soldMedian = median(soldValues);
  const soldTop = Math.max(0.001, ...soldValues.filter((v) => v <= Math.max(5 * soldMedian, 0.02))) * 1.1;
  const soldStep = niceStep(soldTop / 4);
  const soldMax = Math.min(1, Math.ceil(soldTop / soldStep) * soldStep);
  const soldTicks: number[] = [];
  for (let v = 0; v <= soldMax + 1e-9; v += soldStep) soldTicks.push(v);
  const adjValues = pts.map((p) => p.adjusted).filter((v): v is number => v !== null);
  let lo = Math.floor((Math.min(paper, ...adjValues) - 0.005) * 100) / 100;
  let hi = Math.ceil((Math.max(paper, ...adjValues) + 0.005) * 100) / 100;
  if (hi - lo < 0.04) {
    const mid = (hi + lo) / 2;
    lo = Math.floor((mid - 0.02) * 100) / 100;
    hi = lo + 0.04;
  }
  const step = hi - lo > 0.1 ? 0.05 : hi - lo > 0.05 ? 0.02 : 0.01;
  const retTicks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) retTicks.push(Number(v.toFixed(2)));
  const ySold = (v: number) => H - (Math.min(v, soldMax) / soldMax) * H;
  const yRet = (v: number) => H - ((v - lo) / (hi - lo)) * H;

  const soldDigits = soldStep < 0.01 ? 1 : 0;
  const pctLabel = (v: number) =>
    new Intl.NumberFormat(locale === "en" ? "en-IE" : `${locale}-ES`, { style: "percent", maximumFractionDigits: soldDigits, minimumFractionDigits: soldDigits }).format(v);

  // Month ticks: the first of each month inside the range
  const months: number[] = [];
  const d = new Date(t0);
  let m = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
  while (m <= t1) {
    months.push(m);
    const md = new Date(m);
    m = Date.UTC(md.getUTCFullYear(), md.getUTCMonth() + 1, 1);
  }

  const line = (run: P[], key: "sold" | "adjusted", y: (v: number) => number) =>
    run
      .filter((p) => p[key] !== null)
      .map((p) => `${x(p.t).toFixed(1)},${y(p[key] as number).toFixed(1)}`)
      .join(" ");

  const onMove = (e: React.PointerEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    const t = t0 + ((e.clientX - r.left) / r.width) * (t1 - t0);
    let best = 0;
    pts.forEach((p, i) => {
      if (Math.abs(p.t - t) < Math.abs(pts[best].t - t)) best = i;
    });
    setHover(best);
  };
  const hp = hover === null ? null : pts[hover];

  const panel = (
    title: string,
    color: string,
    ticks: number[],
    tickLabel: (v: number) => string,
    y: (v: number) => number,
    key: "sold" | "adjusted",
    extra?: React.ReactNode,
  ) => (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-2 text-[13px] font-semibold text-muted">
        <span aria-hidden="true" className="inline-block h-[3px] w-4 rounded-full" style={{ background: color }} />
        {title}
      </span>
      <div className="relative grid grid-cols-[52px_1fr] gap-2">
        <div className="num relative text-right text-xs text-muted" style={{ height: H }}>
          {ticks.map((v) => (
            <span key={v} className="absolute right-0 -translate-y-1/2" style={{ top: `${(y(v) / H) * 100}%` }}>
              {tickLabel(v)}
            </span>
          ))}
        </div>
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="block w-full overflow-visible" style={{ height: H }} aria-hidden="true">
            {gaps.map(([a, b]) => (
              <rect key={a} x={x(a)} y={0} width={x(b) - x(a)} height={H} fill="var(--color-line-soft)" />
            ))}
            {ticks.map((v) => (
              <line key={v} x1={0} x2={W} y1={y(v)} y2={y(v)} stroke={v === ticks[0] ? "var(--color-control)" : "var(--color-line-soft)"} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ))}
            {extra}
            {runs.map((run, i) => (
              <polyline key={i} points={line(run, key, y)} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            ))}
          </svg>
          {hp && hp[key] !== null && (
            <span
              className="pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card"
              style={{ left: `${xPct(hp.t)}%`, top: `${(y(hp[key] as number) / H) * 100}%`, background: color }}
            />
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={box}
        className="relative ml-[60px] touch-none"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        onPointerDown={onMove}
      >
        {/* hover layer spans both panels */}
        <div className="-ml-[60px] flex flex-col gap-5">
          {panel(labels.soldSeries, SOLD, soldTicks, pctLabel, ySold, "sold")}
          {panel(
            labels.adjSeries,
            RETURN,
            retTicks,
            (v) => fmt.perEuro(v).replace(/(\d)0(\D*)$/, "$1$2"),
            yRet,
            "adjusted",
            <line x1={0} x2={W} y1={yRet(paper)} y2={yRet(paper)} stroke={PAPER} strokeWidth={1.5} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />,
          )}
        </div>
        {hp && (
          <>
            <span className="pointer-events-none absolute top-6 bottom-0 w-px bg-muted/50" style={{ left: `${xPct(hp.t)}%` }} />
            <div
              className="num pointer-events-none absolute top-0 z-10 rounded-lg border border-line bg-card px-3 py-2 text-[13px] shadow-[0_8px_24px_rgba(21,23,28,0.12)]"
              style={xPct(hp.t) > 60 ? { right: `${100 - xPct(hp.t) + 1}%` } : { left: `${xPct(hp.t) + 1}%` }}
            >
              <div className="font-semibold text-ink">{fmt.date(new Date(hp.t).toISOString())}</div>
              <div className="flex items-center gap-2 text-muted">
                <span className="inline-block h-[3px] w-3 rounded-full" style={{ background: SOLD }} />
                {hp.sold === null ? labels.noData : fmt.pct(hp.sold)}
              </div>
              <div className="flex items-center gap-2 text-muted">
                <span className="inline-block h-[3px] w-3 rounded-full" style={{ background: RETURN }} />
                {hp.adjusted === null ? labels.noData : fmt.perEuro(hp.adjusted)}
              </div>
            </div>
          </>
        )}
      </div>
      <div className="relative ml-[60px] h-4 text-xs text-muted">
        {months.map((mt) => (
          <span key={mt} className="absolute -translate-x-1/2" style={{ left: `${xPct(mt)}%` }}>
            {monthFmt.format(new Date(mt))}
          </span>
        ))}
      </div>
      <span className="ml-[60px] flex items-center gap-2 text-[13px] text-muted">
        <svg aria-hidden="true" width="18" height="4">
          <line x1="0" y1="2" x2="18" y2="2" stroke={PAPER} strokeWidth="1.5" strokeDasharray="5 4" />
        </svg>
        {fill(labels.onPaper, { value: fmt.perEuro(paper) })}
      </span>

      {/* the same data as a table, for screen readers */}
      <table className="sr-only">
        <thead>
          <tr>
            <th>Date</th>
            <th>{labels.soldSeries}</th>
            <th>{labels.adjSeries}</th>
          </tr>
        </thead>
        <tbody>
          {pts.map((p) => (
            <tr key={p.t}>
              <td>{fmt.date(new Date(p.t).toISOString())}</td>
              <td>{p.sold === null ? labels.noData : fmt.pct(p.sold)}</td>
              <td>{p.adjusted === null ? labels.noData : fmt.perEuro(p.adjusted)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** Round a step up to 1, 2 or 5 × a power of ten. */
function niceStep(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v));
  for (const f of [1, 2, 5, 10]) if (v <= f * p) return f * p;
  return 10 * p;
}
