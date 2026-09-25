import { useState } from "react";

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

const PALETTE = [
  "#1f4a38",
  "#3d6b54",
  "#8a6a2f",
  "#3d5a80",
  "#9b2c2c",
  "#5c4d7a",
  "#2a6f6f",
  "#6b4f3a",
  "#4a6b2f",
  "#7a4a3d",
  "#2f4a6b",
  "#6b3d5a",
];

const INNER = 27;
const OUTER = 44;
const LABEL_R = 35.5;
const TIP_R = 52;

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
  return Object.fromEntries(unique.map((key, index) => [key, PALETTE[index % PALETTE.length]]));
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
      className={`h-3.5 w-3.5 shrink-0 text-moss transition-transform duration-200 ${open ? "rotate-90" : ""}`}
      aria-hidden="true"
    >
      <path fill="currentColor" d="M6 3.2 11.2 8 6 12.8V3.2Z" />
    </svg>
  );
}

type SliceArc = {
  itemKey: string;
  d: string;
  color: string;
  start: number;
  end: number;
  slice: PieSlice;
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
  const amounts = slices.map((item) => Number(item.value) || 0);
  const sum = amounts.reduce((acc, item) => acc + item, 0);
  let cursor = 0;
  const arcs: SliceArc[] = slices.flatMap((item, index) => {
    const amount = amounts[index];
    const sweep = sum > 0 ? (amount / sum) * 360 : 0;
    const start = cursor;
    const end = index === slices.length - 1 ? 360 : cursor + sweep;
    cursor = end;
    if (sweep <= 0) {
      return [];
    }
    const color = colors[item.key] ?? PALETTE[index % PALETTE.length];
    return slicePaths(INNER, OUTER, start, end).map((d) => ({
      itemKey: item.key || "unknown",
      d,
      color,
      start,
      end,
      slice: item,
    }));
  });
  const labeled = new Map<string, { mid: number; slice: PieSlice }>();
  for (const arc of arcs) {
    if (labeled.has(arc.itemKey)) {
      continue;
    }
    if (Number(arc.slice.share) < 6) {
      continue;
    }
    labeled.set(arc.itemKey, {
      mid: arc.end - arc.start >= 359.999 ? 0 : (arc.start + arc.end) / 2,
      slice: arc.slice,
    });
  }
  const active = hovered ? slices.find((item) => (item.key || "unknown") === hovered) : null;
  const tip = active
    ? (() => {
        const arc = arcs.find((item) => item.itemKey === hovered);
        if (!arc) {
          return null;
        }
        const [x, y] = polar(TIP_R, (arc.start + arc.end) / 2);
        return { x, y, slice: active };
      })()
    : null;

  const toggleSector = (itemKey: string) => {
    setOpenSectors((current) =>
      current.includes(itemKey) ? current.filter((key) => key !== itemKey) : [...current, itemKey],
    );
  };

  return (
    <article className="border border-line bg-paper-2/40 p-5">
      <h2 className="font-display text-2xl">{title}</h2>
      {slices.length === 0 ? (
        <p className="mt-6 text-sm text-moss">{emptyHint}</p>
      ) : (
        <div className="mt-5 space-y-5">
          <div className="relative mx-auto aspect-square w-full max-w-lg">
            <svg
              viewBox="0 0 100 100"
              className="h-full w-full"
              role="img"
              aria-label={title}
              onMouseLeave={() => setHovered(null)}
            >
              {arcs.map((arc, index) => (
                <path
                  key={`${arc.itemKey}-${index}`}
                  d={arc.d}
                  fill={arc.color}
                  className="cursor-pointer"
                  opacity={hovered && hovered !== arc.itemKey ? 0.38 : 1}
                  onMouseOver={() => setHovered(arc.itemKey)}
                />
              ))}
              {[...labeled.values()].map(({ mid, slice }) => {
                const [x, y] = polar(LABEL_R, mid);
                return (
                  <text
                    key={`label-${slice.key || "unknown"}`}
                    x={x}
                    y={y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="#f4f0e6"
                    fontSize="4.2"
                    fontWeight="600"
                    className="pointer-events-none"
                  >
                    {formatShare(slice.share)}
                  </text>
                );
              })}
            </svg>
            <div className="pointer-events-none absolute inset-[28%] flex flex-col items-center justify-center text-center">
              <p className="text-[0.7rem] uppercase tracking-[0.14em] text-moss">бумаги</p>
              <p className="mt-1 font-display text-2xl leading-tight sm:text-3xl">{formatMoneyCenter(total)}</p>
            </div>
            {tip ? (
              <div
                className="pointer-events-none absolute z-10 whitespace-nowrap border border-line bg-paper px-2 py-1 text-xs shadow-sm"
                style={{
                  left: `${tip.x}%`,
                  top: `${tip.y}%`,
                  transform: "translate(-50%, -50%)",
                }}
              >
                <span className="text-ink">{tip.slice.label}</span>
                <span className="ml-2 font-display text-forest">{formatShare(tip.slice.share)}</span>
              </div>
            ) : null}
          </div>

          <div>
            <button
              type="button"
              className="flex w-full items-center gap-2 py-1 text-sm text-moss hover:text-forest"
              aria-expanded={listOpen}
              onClick={() => setListOpen((open) => !open)}
            >
              <Chevron open={listOpen} />
              <span>Категории</span>
              <span className="ml-auto text-xs">
                {slices.length} {sectorsWord(slices.length)}
              </span>
            </button>
            {listOpen ? (
              <ul className="mt-2 space-y-1 text-sm">
                {slices.map((item) => {
                  const itemKey = item.key || "unknown";
                  const papers = item.holdings ?? [];
                  const sectorOpen = openSectors.includes(itemKey);
                  const dimmed = hovered != null && hovered !== itemKey;
                  return (
                    <li
                      key={itemKey}
                      className={dimmed ? "opacity-40" : ""}
                      onMouseEnter={() => setHovered(itemKey)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <button
                        type="button"
                        className="flex w-full items-start gap-2 py-1.5 text-left hover:text-forest"
                        aria-expanded={sectorOpen}
                        onClick={() => toggleSector(itemKey)}
                      >
                        <Chevron open={sectorOpen} />
                        <span
                          className="mt-1 inline-block h-2.5 w-2.5 shrink-0"
                          style={{ background: colors[item.key] ?? PALETTE[0] }}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{item.label}</span>
                          {item.holdings_count != null ? (
                            <span className="text-xs text-moss">
                              {item.holdings_count} {papersWord(item.holdings_count)}
                            </span>
                          ) : null}
                        </span>
                        <span className="shrink-0 text-right">
                          <span className="block">{formatShare(item.share)}</span>
                          <span className="text-xs text-moss">{formatMoney(item.value)}</span>
                        </span>
                      </button>
                      {sectorOpen ? (
                        papers.length === 0 ? (
                          <p className="mb-2 ml-9 text-xs text-moss">Нет бумаг в этой отрасли.</p>
                        ) : (
                          <ul className="mb-2 ml-9 space-y-1 border-l border-line pl-3">
                            {papers.map((paper) => (
                              <li key={paper.figi} className="flex items-start justify-between gap-3 py-1">
                                <span className="min-w-0">
                                  <span className="block truncate">{paper.ticker}</span>
                                  <span className="block truncate text-xs text-moss">{paper.name}</span>
                                </span>
                                <span className="shrink-0 text-right">
                                  <span className="block">{formatShare(paper.share)}</span>
                                  <span className="text-xs text-moss">{formatMoney(paper.value)}</span>
                                </span>
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
