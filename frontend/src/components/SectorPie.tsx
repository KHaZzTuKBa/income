import { useState, useMemo, useRef, useEffect, useId } from "react";

export type PiePaper = {
  figi: string;
  ticker: string;
  name: string;
  value: string;
  share: string;
};

export type PieSlice = {
  key: string;
  label: string;
  value: string;
  share: string;
  holdings_count?: number;
  holdings?: PiePaper[];
};

// High-contrast, vibrant, and harmonized Material 3 palette for data visualization.
// Excludes dull, pale translucent greens to keep sectors clearly distinguishable.
const PALETTE = [
  "#3730a3", // Deep Indigo
  "#ea580c", // Warm Coral / Tangerine
  "#0d9488", // Vibrant Teal
  "#7e22ce", // Royal Purple
  "#be123c", // Deep Burgundy / Crimson
  "#0284c7", // Ocean Blue
  "#d97706", // Warm Amber
  "#a21caf", // Rich Magenta / Plum
  "#0369a1", // Deep Sapphire
  "#c2410c", // Burnt Terracotta
  "#4338ca", // Classic Indigo
  "#0891b2", // Vibrant Cyan
  "#9f1239", // Wine Rose
  "#6366f1", // Electric Violet
  "#b45309", // Warm Ochre
  "#475569", // Slate Navy
];

const INNER = 28;
const OUTER = 44;
const LABEL_R = 36;
const TIP_R = 54;

export function sectorColors(keys: string[]): Record<string, string> {
  const unique = [...new Set(keys)];
  unique.sort((left, right) => {
    if (!left && right) {
      return 1;
    }
    if (left && !right) {
      return -1;
    }
    return left.localeCompare(right, "ru");
  });
  return Object.fromEntries(
    unique.map((key, index) => [
      key,
      !key ? "#64748b" : PALETTE[index % PALETTE.length],
    ])
  );
}

function formatMoney(value: string | number): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(parsed)) {
    return "—";
  }
  return `${parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ₽`;
}

function formatMoneyCenter(value: string | number): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(parsed)) {
    return "—";
  }
  return `${parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })} ₽`;
}

function formatShare(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return `${parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
}

function papersWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return "бумага";
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "бумаги";
  }
  return "бумаг";
}

function sectorsWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return "отрасль";
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "отрасли";
  }
  return "отраслей";
}

function polar(radius: number, angle: number): [number, number] {
  const radians = ((angle - 90) * Math.PI) / 180;
  return [50 + radius * Math.cos(radians), 50 + radius * Math.sin(radians)];
}

function donutPath(inner: number, outer: number, start: number, end: number): string {
  const sweep = end - start;
  const large = sweep > 180 ? 1 : 0;
  const [x1, y1] = polar(outer, start);
  const [x2, y2] = polar(outer, end);
  const [x3, y3] = polar(inner, end);
  const [x4, y4] = polar(inner, start);
  return `M ${x1} ${y1} A ${outer} ${outer} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${inner} ${inner} 0 ${large} 0 ${x4} ${y4} Z`;
}

function slicePaths(inner: number, outer: number, start: number, end: number): string[] {
  if (end - start >= 359.999) {
    return [donutPath(inner, outer, 0, 180), donutPath(inner, outer, 180, 360)];
  }
  return [donutPath(inner, outer, start, end)];
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className={`h-3.5 w-3.5 shrink-0 text-emerald-700 transition-transform duration-200 ${
        open ? "rotate-90" : ""
      }`}
      aria-hidden="true"
    >
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6 3.5l4.5 4.5L6 12.5"
      />
    </svg>
  );
}

type SectorGroup = {
  itemKey: string;
  paths: string[];
  color: string;
  start: number;
  end: number;
  mid: number;
  slice: PieSlice;
  label?: { x: number; y: number };
};

export function SectorPie({
  title,
  total,
  slices,
  colors,
  emptyHint,
}: {
  title: string;
  total: string;
  slices: PieSlice[];
  colors: Record<string, string>;
  emptyHint: string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const [openSectors, setOpenSectors] = useState<string[]>([]);
  const [highlightedSector, setHighlightedSector] = useState<string | null>(null);
  const [scrollTarget, setScrollTarget] = useState<{ key: string; ts: number } | null>(null);
  const sectorRefs = useRef<Map<string, HTMLElement>>(new Map());
  const uniqueId = useId();

  const amounts = useMemo(() => slices.map((item) => Number(item.value) || 0), [slices]);
  const sum = useMemo(() => amounts.reduce((acc, item) => acc + item, 0), [amounts]);

  const handleSectorClick = (itemKey: string) => {
    setListOpen(true);
    setOpenSectors((current) =>
      current.includes(itemKey) ? current : [...current, itemKey],
    );
    setHighlightedSector(itemKey);
    setScrollTarget({ key: itemKey, ts: Date.now() });
  };

  useEffect(() => {
    if (!scrollTarget) return;
    const timer = setTimeout(() => {
      const el = sectorRefs.current.get(scrollTarget.key);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 80);
    return () => clearTimeout(timer);
  }, [scrollTarget]);

  useEffect(() => {
    if (!highlightedSector) return;
    const timer = setTimeout(() => {
      setHighlightedSector(null);
    }, 2200);
    return () => clearTimeout(timer);
  }, [highlightedSector]);

  const sectorGroups: SectorGroup[] = useMemo(() => {
    let cursor = 0;
    return slices.flatMap((item, index) => {
      const amount = amounts[index];
      const sweep = sum > 0 ? (amount / sum) * 360 : 0;
      const start = cursor;
      const end = index === slices.length - 1 ? 360 : cursor + sweep;
      cursor = end;
      if (sweep <= 0) {
        return [];
      }
      const itemKey = item.key || "unknown";
      const color = colors[item.key] ?? (!item.key ? "#64748b" : PALETTE[index % PALETTE.length]);
      const paths = slicePaths(INNER, OUTER, start, end);
      const mid = end - start >= 359.999 ? 0 : (start + end) / 2;
      const showLabel = Number(item.share) >= 6;
      const labelCoords = showLabel ? polar(LABEL_R, mid) : null;

      return [
        {
          itemKey,
          paths,
          color,
          start,
          end,
          mid,
          slice: item,
          label: labelCoords ? { x: labelCoords[0], y: labelCoords[1] } : undefined,
        },
      ];
    });
  }, [amounts, colors, slices, sum]);

  const active = hovered ? slices.find((item) => (item.key || "unknown") === hovered) : null;
  const tip = active
    ? (() => {
        const group = sectorGroups.find((item) => item.itemKey === hovered);
        if (!group) {
          return null;
        }
        const [x, y] = polar(TIP_R, group.mid);
        const tipX = Math.max(16, Math.min(84, x));
        const tipY = Math.max(12, Math.min(88, y));
        return { x: tipX, y: tipY, slice: active, color: group.color };
      })()
    : null;

  const toggleSector = (itemKey: string) => {
    setOpenSectors((current) =>
      current.includes(itemKey) ? current.filter((key) => key !== itemKey) : [...current, itemKey],
    );
  };

  const filterId = `sector-shadow-${uniqueId.replace(/[^a-zA-Z0-9_-]/g, "")}`;

  return (
    <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 sm:p-7 shadow-[0_4px_24px_-4px_rgba(16,185,129,0.06),0_2px_8px_-2px_rgba(0,0,0,0.02)] transition-all">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-emerald-500/10 pb-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-xs shadow-emerald-500/40" />
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">{title}</h2>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-emerald-500/10 px-3.5 py-1 text-xs font-semibold text-emerald-800">
          <span>{slices.length} {sectorsWord(slices.length)}</span>
        </div>
      </div>

      {slices.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">{emptyHint}</p>
      ) : (
        <div className="mt-6 space-y-6">
          <div className="relative mx-auto aspect-square w-full max-w-md">
            <svg
              viewBox="0 0 100 100"
              className="h-full w-full overflow-visible"
              role="img"
              aria-label={title}
              onMouseLeave={() => setHovered(null)}
            >
              <defs>
                <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
                  <feDropShadow dx="0" dy="1.5" stdDeviation="1.8" floodColor="#0f172a" floodOpacity="0.22" />
                </filter>
              </defs>
              {sectorGroups.map((group) => {
                const isHovered = hovered === group.itemKey;
                return (
                  <g
                    key={group.itemKey}
                    role="button"
                    tabIndex={0}
                    aria-label={`Открыть детализацию отрасли ${group.slice.label}`}
                    className="cursor-pointer focus:outline-none"
                    style={{
                      transformBox: "view-box",
                      transformOrigin: "50px 50px",
                      transform: isHovered ? "scale(1.048)" : "scale(1)",
                      transition: "transform 250ms cubic-bezier(0.16, 1, 0.3, 1), opacity 200ms ease-out",
                      opacity: hovered && !isHovered ? 0.35 : 1,
                    }}
                    filter={isHovered ? `url(#${filterId})` : undefined}
                    onMouseEnter={() => setHovered(group.itemKey)}
                    onClick={() => handleSectorClick(group.itemKey)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSectorClick(group.itemKey);
                      }
                    }}
                  >
                    {group.paths.map((d, pIdx) => (
                      <path
                        key={pIdx}
                        d={d}
                        fill={group.color}
                        stroke="#ffffff"
                        strokeWidth="0.8"
                        strokeLinejoin="round"
                      />
                    ))}
                    {group.label ? (
                      <text
                        x={group.label.x}
                        y={group.label.y}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill="#ffffff"
                        fontSize="3.8"
                        fontWeight="700"
                        className="pointer-events-none select-none"
                        style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}
                      >
                        {formatShare(group.slice.share)}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </svg>

            <div className="pointer-events-none absolute inset-[27%] flex flex-col items-center justify-center text-center rounded-full bg-white/90 backdrop-blur-xs border border-emerald-500/10 shadow-xs p-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                {active ? "Сектор" : "Бумаги"}
              </p>
              <p className="mt-0.5 font-extrabold tracking-tight text-slate-900 text-lg sm:text-2xl leading-tight">
                {active ? formatMoneyCenter(active.value) : formatMoneyCenter(total)}
              </p>
              {active ? (
                <span className="mt-1 inline-flex items-center rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                  {formatShare(active.share)}
                </span>
              ) : (
                <p className="mt-0.5 text-[10px] text-slate-400 font-medium">без кэша</p>
              )}
            </div>

            {tip ? (
              <div
                className="pointer-events-none absolute z-30 whitespace-nowrap rounded-2xl border border-emerald-500/20 bg-white/95 px-3.5 py-2.5 shadow-xl shadow-slate-900/10 backdrop-blur-md transition-all duration-150 ease-out"
                style={{
                  left: `${tip.x}%`,
                  top: `${tip.y}%`,
                  transform: "translate(-50%, -50%)",
                }}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full shadow-xs"
                    style={{ backgroundColor: tip.color }}
                  />
                  <span className="text-xs font-semibold text-slate-800">{tip.slice.label}</span>
                </div>
                <div className="mt-1.5 flex items-baseline justify-between gap-3 text-xs">
                  <span className="font-bold text-slate-900 font-mono">{formatMoney(tip.slice.value)}</span>
                  <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-bold text-emerald-800">
                    {formatShare(tip.slice.share)}
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-emerald-700/80 font-medium">
                  Нажмите, чтобы открыть детализацию
                </p>
              </div>
            ) : null}
          </div>

          <div className="border-t border-emerald-500/10 pt-4">
            <button
              type="button"
              className="flex w-full items-center justify-between rounded-2xl bg-emerald-500/[0.04] hover:bg-emerald-500/[0.08] px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors border border-emerald-500/10"
              aria-expanded={listOpen}
              onClick={() => setListOpen((open) => !open)}
            >
              <div className="flex items-center gap-2.5">
                <Chevron open={listOpen} />
                <span className="font-semibold text-slate-800">Детализация по отраслям</span>
              </div>
              <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
                {slices.length} {sectorsWord(slices.length)}
              </span>
            </button>
            {listOpen ? (
              <ul className="mt-3 space-y-1 text-sm">
                {slices.map((item) => {
                  const itemKey = item.key || "unknown";
                  const papers = item.holdings ?? [];
                  const sectorOpen = openSectors.includes(itemKey);
                  const isHovered = hovered === itemKey;
                  const isHighlighted = highlightedSector === itemKey;
                  const dimmed = hovered != null && !isHovered;
                  const sectorColor = colors[item.key] ?? (!item.key ? "#64748b" : PALETTE[0]);
                  return (
                    <li
                      key={itemKey}
                      ref={(node) => {
                        if (node) {
                          sectorRefs.current.set(itemKey, node);
                        } else {
                          sectorRefs.current.delete(itemKey);
                        }
                      }}
                      className={`scroll-mt-24 rounded-2xl transition-all duration-300 ${
                        isHighlighted
                          ? "bg-emerald-500/[0.14] ring-2 ring-emerald-500/50 shadow-sm"
                          : isHovered
                            ? "bg-emerald-500/[0.08]"
                            : "hover:bg-emerald-500/[0.04]"
                      } ${dimmed && !isHighlighted ? "opacity-35" : ""}`}
                      onMouseEnter={() => setHovered(itemKey)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <button
                        type="button"
                        className="flex w-full items-center gap-3 p-2.5 text-left"
                        aria-expanded={sectorOpen}
                        onClick={() => toggleSector(itemKey)}
                      >
                        <Chevron open={sectorOpen} />
                        <span
                          className="h-3 w-3 shrink-0 rounded-full shadow-xs"
                          style={{ backgroundColor: sectorColor }}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium text-slate-900">{item.label}</span>
                          {item.holdings_count != null ? (
                            <span className="text-xs text-slate-500">
                              {item.holdings_count} {papersWord(item.holdings_count)}
                            </span>
                          ) : null}
                        </span>
                        <div className="flex shrink-0 items-center gap-3 text-right">
                          <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-bold text-emerald-800">
                            {formatShare(item.share)}
                          </span>
                          <span className="text-xs font-semibold text-slate-700 min-w-20 text-right">
                            {formatMoney(item.value)}
                          </span>
                        </div>
                      </button>
                      {sectorOpen ? (
                        papers.length === 0 ? (
                          <p className="mb-2 ml-10 text-xs text-slate-400">Нет бумаг в этой отрасли.</p>
                        ) : (
                          <ul className="mb-2 ml-8 space-y-1.5 rounded-2xl bg-slate-50/80 p-3 border border-emerald-500/10">
                            {papers.map((paper) => (
                              <li key={paper.figi} className="flex items-center justify-between gap-3 px-2 py-1 hover:bg-white rounded-xl transition-colors">
                                <span className="min-w-0">
                                  <span className="block truncate font-semibold text-xs text-slate-900">{paper.ticker}</span>
                                  <span className="block truncate text-xs text-slate-500">{paper.name}</span>
                                </span>
                                <div className="flex shrink-0 items-center gap-2.5 text-right">
                                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 border border-slate-200/60 shadow-xs">
                                    {formatShare(paper.share)}
                                  </span>
                                  <span className="text-xs font-semibold text-slate-800 min-w-18 text-right">
                                    {formatMoney(paper.value)}
                                  </span>
                                </div>
                              </li>
                            ))}
                          </ul>
                        )
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
        </div>
      )}
    </article>
  );
}
