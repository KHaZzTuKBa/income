import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getHistory, type HistoryGranularity, type HistoryPeriod, type HistoryPoint, type HistorySeries } from "../api/history";

type ChartPoint = {
  day: string;
  value: number;
  invested: number;
  imoex: number | null;
};

const PERIODS: { id: HistoryPeriod; label: string }[] = [
  { id: "week", label: "Неделя" },
  { id: "month", label: "Месяц" },
  { id: "year", label: "Календарный год" },
  { id: "6m", label: "Полгода" },
  { id: "1y", label: "12 месяцев" },
  { id: "all", label: "Всё время" },
  { id: "custom", label: "Свой диапазон" },
];

function num(value: string | null | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value: number): string {
  return `${value.toLocaleString("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })} ₽`;
}

function formatMoneyExact(value: number): string {
  return `${value.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ₽`;
}

function formatSignedMoney(value: number): string {
  const formatted = formatMoneyExact(value);
  return value > 0 ? `+${formatted}` : formatted;
}

function moneyClass(value: number): string {
  if (value === 0) {
    return "";
  }
  return value > 0 ? "text-gain" : "text-danger";
}

function formatPercent(value: number): string {
  const formatted = value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  return `${value > 0 ? "+" : ""}${formatted}%`;
}

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatBucket(value: string, granularity: HistoryGranularity): string {
  const date = new Date(`${value}T00:00:00`);
  if (granularity === "month") {
    return date.toLocaleDateString("ru-RU", { month: "short", year: "numeric" });
  }
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function defaultCustomRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 29);
  return { from: isoDate(from), to: isoDate(to) };
}

export function PortfolioCharts({ enabled }: { enabled: boolean }) {
  const [period, setPeriod] = useState<HistoryPeriod>("all");
  const [year, setYear] = useState(new Date().getFullYear());
  const [custom, setCustom] = useState(defaultCustomRange);

  const history = useQuery({
    queryKey: ["history", period, year, custom.from, custom.to],
    queryFn: () =>
      getHistory({
        period,
        year: period === "year" ? year : undefined,
        from: period === "custom" ? custom.from : undefined,
        to: period === "custom" ? custom.to : undefined,
      }),
    enabled,
    refetchInterval: (query) => (query.state.data?.building ? 5000 : 60_000),
  });

  const years = useMemo(() => {
    const fromApi = history.data?.years ?? [];
    return [...new Set([...fromApi, year, new Date().getFullYear()])].sort((a, b) => a - b);
  }, [history.data?.years, year]);
  const granularity = history.data?.granularity ?? (period === "week" || period === "month" ? "day" : "month");
  const series = (history.data?.series ?? []).filter(
    (item) => item.account_id == null || item.points.some((point) => num(point.value) !== 0 || num(point.invested) !== 0)
  );
  const building = history.data?.building === true;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-display text-2xl">Стоимость во времени</h2>
        <div className="flex flex-wrap items-center gap-2">
          {PERIODS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setPeriod(item.id)}
              className={`border px-3 py-1 text-xs ${
                period === item.id ? "border-forest text-forest" : "border-line text-moss hover:border-forest"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {period === "year" ? (
        <label className="mt-3 flex items-center gap-2 text-sm text-moss">
          Год
          <select
            className="border border-line bg-paper px-2 py-1 text-ink"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          >
            {years.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {period === "custom" ? (
        <div className="mt-3 flex flex-wrap gap-3 text-sm text-moss">
          <label className="flex items-center gap-2">
            С
            <input
              type="date"
              className="border border-line bg-paper px-2 py-1 text-ink"
              value={custom.from}
              onChange={(event) => setCustom((prev) => ({ ...prev, from: event.target.value }))}
            />
          </label>
          <label className="flex items-center gap-2">
            По
            <input
              type="date"
              className="border border-line bg-paper px-2 py-1 text-ink"
              value={custom.to}
              onChange={(event) => setCustom((prev) => ({ ...prev, to: event.target.value }))}
            />
          </label>
        </div>
      ) : null}
      {history.isError ? (
        <p className="mt-3 text-sm text-danger">
          {history.error instanceof Error ? history.error.message : "Не удалось загрузить график"}
        </p>
      ) : null}
      <div className="mt-4 space-y-6">
        {series.length === 0 ? (
          <div className="border border-line bg-paper-2/30 p-4">
            <p className="text-sm text-moss">
              {building
                ? "Строим историю стоимости по операциям и дневным ценам…"
                : "График появится после обновления портфеля."}
            </p>
          </div>
        ) : (
          series.map((item) => (
            <article key={item.account_id ?? "all"} className="border border-line bg-paper-2/30 p-4">
              <ValueBarChart
                title={item.account_name}
                series={item}
                granularity={granularity}
                showImoex={item.account_id == null}
                building={building}
              />
            </article>
          ))
        )}
      </div>
    </div>
  );
}

function ValueBarChart({
  title,
  series,
  granularity,
  showImoex,
  building,
}: {
  title: string;
  series: HistorySeries;
  granularity: HistoryGranularity;
  showImoex: boolean;
  building: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const points = useMemo(() => toChartPoints(series.points, showImoex), [series.points, showImoex]);

  if (series.points.length === 0) {
    return (
      <div>
        <h3 className="font-display text-xl">{title}</h3>
        <p className="mt-2 text-sm text-moss">
          {building ? "Строим историю стоимости…" : "Нет точек за выбранный период."}
        </p>
      </div>
    );
  }

  const width = 720;
  const height = 260;
  const pad = { top: 16, right: 16, bottom: 36, left: 64 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const values = points.flatMap((item) => [item.value, item.invested, item.imoex ?? 0]);
  const minV = Math.min(0, ...values);
  const maxV = Math.max(...values, 1);
  const span = maxV - minV || 1;
  const slot = innerW / points.length;
  const barW = Math.max(2, slot * 0.7);
  const x = (index: number) => pad.left + slot * index + (slot - barW) / 2;
  const y = (value: number) => pad.top + innerH - ((value - minV) / span) * innerH;
  const zero = y(0);
  const active = points[hover ?? points.length - 1];
  const ticks = 4;
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  const openValue = num(series.open_value);
  const openInvested = num(series.open_invested);
  const investedPeriod = active.invested - openInvested;
  const profitPeriod = active.value - active.invested - (openValue - openInvested);
  const profitPercent =
    investedPeriod !== 0 ? (profitPeriod / investedPeriod) * 100 : openValue !== 0 ? (profitPeriod / openValue) * 100 : null;

  const investedPath = points
    .map((item, index) => `${index === 0 ? "M" : "L"} ${(x(index) + barW / 2).toFixed(1)} ${y(item.invested).toFixed(1)}`)
    .join(" ");
  const imoexPath = points
    .map((item, index) =>
      item.imoex == null
        ? null
        : `${index === 0 || points[index - 1]?.imoex == null ? "M" : "L"} ${(x(index) + barW / 2).toFixed(1)} ${y(item.imoex).toFixed(1)}`
    )
    .filter(Boolean)
    .join(" ");

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-display text-xl">{title}</h3>
          <p className="font-display text-2xl">{formatMoney(active.value)}</p>
          <p className="text-xs text-moss">{formatBucket(active.day, granularity)}</p>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="mt-3 w-full"
        style={{ aspectRatio: `${width} / ${height}` }}
        onMouseLeave={() => setHover(null)}
      >
        {[...Array(ticks + 1)].map((_, index) => {
          const value = minV + (span * index) / ticks;
          const pos = y(value);
          return (
            <g key={index}>
              <line x1={pad.left} x2={width - pad.right} y1={pos} y2={pos} stroke="#d4ccb8" strokeWidth="1" />
              <text x={pad.left - 8} y={pos + 4} textAnchor="end" className="fill-moss" fontSize="10">
                {formatMoney(value)}
              </text>
            </g>
          );
        })}
        {points.map((item, index) => {
          const top = y(Math.max(item.value, 0));
          const bottom = item.value >= 0 ? zero : y(item.value);
          const barHeight = Math.max(1, Math.abs(bottom - top));
          return (
            <rect
              key={item.day}
              x={x(index)}
              y={Math.min(top, bottom)}
              width={barW}
              height={barHeight}
              fill={index === (hover ?? points.length - 1) ? "#163628" : "#1f4a38"}
            />
          );
        })}
        <path d={investedPath} fill="none" stroke="#3d6b54" strokeWidth="1.5" strokeDasharray="5 4" />
        {showImoex && imoexPath ? <path d={imoexPath} fill="none" stroke="#9b2c2c" strokeWidth="1.5" /> : null}
        {points.map((item, index) =>
          index % labelEvery === 0 || index === points.length - 1 ? (
            <text
              key={`label-${item.day}`}
              x={x(index) + barW / 2}
              y={height - 8}
              textAnchor="middle"
              className="fill-moss"
              fontSize="10"
            >
              {formatBucket(item.day, granularity)}
            </text>
          ) : null
        )}
        {points.map((item, index) => (
          <rect
            key={`hit-${item.day}`}
            x={pad.left + slot * index}
            y={0}
            width={slot}
            height={height}
            fill="none"
            pointerEvents="all"
            className="cursor-crosshair"
            onMouseEnter={() => setHover(index)}
          />
        ))}
      </svg>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <article className="border border-line bg-paper/70 p-3">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Вложено</p>
          <p className="mt-1 font-display text-xl">{formatSignedMoney(investedPeriod)}</p>
          <p className="mt-1 text-xs text-moss">Чистые вводы − выводы за период</p>
        </article>
        <article className="border border-line bg-paper/70 p-3">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Прибыль</p>
          <p className={`mt-1 font-display text-xl ${moneyClass(profitPeriod)}`}>{formatSignedMoney(profitPeriod)}</p>
          <p className={`mt-1 text-xs ${moneyClass(profitPeriod) || "text-moss"}`}>
            {profitPercent != null
              ? `${formatPercent(profitPercent)} · изменение стоимости − вводы`
              : "Изменение стоимости − вводы за период"}
          </p>
        </article>
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-moss">
        <span>
          <span className="mr-1 inline-block h-2 w-4 bg-forest align-middle" />
          стоимость на конец периода
        </span>
        <span>
          <span className="mr-1 inline-block h-0.5 w-4 border-t border-dashed border-moss align-middle" />
          вложено
        </span>
        {showImoex && points.some((item) => item.imoex != null) ? (
          <span>
            <span className="mr-1 inline-block h-0.5 w-4 bg-danger align-middle" />
            IMOEX к старту периода
          </span>
        ) : null}
      </div>
    </div>
  );
}

function toChartPoints(points: HistoryPoint[], showImoex: boolean): ChartPoint[] {
  const first = points.find((item) => num(item.value) > 0 && item.imoex != null && num(item.imoex) > 0);
  const scale = showImoex && first ? num(first.value) / num(first.imoex) : 0;
  return points.map((item) => ({
    day: item.day,
    value: num(item.value),
    invested: num(item.invested),
    imoex: showImoex && item.imoex != null && scale > 0 ? num(item.imoex) * scale : null,
  }));
}
