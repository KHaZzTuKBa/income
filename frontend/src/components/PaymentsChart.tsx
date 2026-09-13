import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getCalendarPayments,
  type PaymentGranularity,
  type PaymentHistoryPoint,
  type PaymentPeriod,
} from "../api/calendar";

const PERIODS: { id: PaymentPeriod; label: string }[] = [
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

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatBucket(value: string, granularity: PaymentGranularity): string {
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

export function PaymentsChart({ enabled }: { enabled: boolean }) {
  const [period, setPeriod] = useState<PaymentPeriod>("all");
  const [year, setYear] = useState(new Date().getFullYear());
  const [custom, setCustom] = useState(defaultCustomRange);

  const payments = useQuery({
    queryKey: ["calendar-payments", period, year, custom.from, custom.to],
    queryFn: () =>
      getCalendarPayments({
        period,
        year: period === "year" ? year : undefined,
        from: period === "custom" ? custom.from : undefined,
        to: period === "custom" ? custom.to : undefined,
      }),
    enabled,
  });

  const years = useMemo(() => {
    const fromApi = payments.data?.years ?? [];
    return [...new Set([...fromApi, year, new Date().getFullYear()])].sort((a, b) => a - b);
  }, [payments.data?.years, year]);
  const granularity = payments.data?.granularity ?? (period === "week" || period === "month" ? "day" : "month");
  const points = payments.data?.points ?? [];
  const total = num(payments.data?.total);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-display text-2xl">Выплаты во времени</h2>
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
      {payments.isError ? (
        <p className="mt-3 text-sm text-danger">
          {payments.error instanceof Error ? payments.error.message : "Не удалось загрузить график выплат"}
        </p>
      ) : null}
      <div className="mt-4">
        {payments.isLoading && points.length === 0 ? (
          <div className="border border-line bg-paper-2/30 p-4">
            <p className="text-sm text-moss">Загружаем выплаты…</p>
          </div>
        ) : points.length === 0 ? (
          <div className="border border-line bg-paper-2/30 p-4">
            <p className="text-sm text-moss">Нет выплат за выбранный период.</p>
          </div>
        ) : (
          <article className="border border-line bg-paper-2/30 p-4">
            <PaymentBarChart points={points} granularity={granularity} total={total} />
          </article>
        )}
      </div>
    </div>
  );
}

function PaymentBarChart({
  points,
  granularity,
  total,
}: {
  points: PaymentHistoryPoint[];
  granularity: PaymentGranularity;
  total: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const values = points.map((item) => num(item.amount));
  const width = 720;
  const height = 260;
  const pad = { top: 16, right: 16, bottom: 36, left: 64 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const minV = 0;
  const maxV = Math.max(...values, 1);
  const span = maxV - minV || 1;
  const slot = innerW / points.length;
  const barW = Math.max(2, slot * 0.7);
  const x = (index: number) => pad.left + slot * index + (slot - barW) / 2;
  const y = (value: number) => pad.top + innerH - ((value - minV) / span) * innerH;
  const zero = y(0);
  const activeIndex = hover ?? points.length - 1;
  const active = points[activeIndex];
  const activeAmount = num(active?.amount);
  const ticks = 4;
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-display text-2xl">{formatMoneyExact(activeAmount)}</p>
          <p className="text-xs text-moss">{active ? formatBucket(active.day, granularity) : ""}</p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Всего за период</p>
          <p className="mt-1 font-display text-xl">{formatMoney(total)}</p>
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
          const top = y(Math.max(values[index], 0));
          const barHeight = Math.max(values[index] > 0 ? 1 : 0, Math.abs(zero - top));
          return (
            <rect
              key={item.day}
              x={x(index)}
              y={Math.min(top, zero)}
              width={barW}
              height={barHeight}
              fill={index === activeIndex ? "#163628" : "#1f4a38"}
            />
          );
        })}
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
      <p className="mt-2 text-xs text-moss">
        <span className="mr-1 inline-block h-2 w-4 bg-forest align-middle" />
        полученные дивиденды и купоны
      </p>
    </div>
  );
}
