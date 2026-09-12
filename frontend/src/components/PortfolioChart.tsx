import { useMemo, useState } from "react";
import type { HistoryPoint } from "../api/history";

type Period = "1y" | "all";

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

function formatDay(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function cutoffFor(period: Period): string | null {
  if (period === "all") {
    return null;
  }
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - 1);
  return cutoff.toISOString().slice(0, 10);
}

export function PortfolioChart({
  points,
  building,
}: {
  points: HistoryPoint[];
  building: boolean;
}) {
  const [period, setPeriod] = useState<Period>("all");
  const [hover, setHover] = useState<number | null>(null);

  const series = useMemo(() => {
    const cutoff = cutoffFor(period);
    const filtered = cutoff ? points.filter((item) => item.day >= cutoff) : points;
    const first = filtered.find((item) => num(item.value) > 0 && item.imoex != null && num(item.imoex) > 0);
    const scale = first ? num(first.value) / num(first.imoex) : 0;
    return filtered.map((item) => ({
      day: item.day,
      value: num(item.value),
      invested: num(item.invested),
      imoex: item.imoex != null && scale > 0 ? num(item.imoex) * scale : null,
    }));
  }, [points, period]);

  if (points.length === 0) {
    return (
      <p className="text-sm text-moss">
        {building
          ? "Строим историю стоимости по операциям и дневным ценам…"
          : "График появится после обновления портфеля."}
      </p>
    );
  }
  if (series.length === 0) {
    return <p className="text-sm text-moss">Нет точек за выбранный период.</p>;
  }

  const width = 720;
  const height = 260;
  const pad = { top: 16, right: 16, bottom: 28, left: 64 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const values = series.flatMap((item) => [item.value, item.invested, item.imoex ?? item.value]);
  const minV = Math.min(0, ...values);
  const maxV = Math.max(...values, 1);
  const span = maxV - minV || 1;
  const x = (index: number) =>
    pad.left + (series.length === 1 ? innerW / 2 : (index / (series.length - 1)) * innerW);
  const y = (value: number) => pad.top + innerH - ((value - minV) / span) * innerH;

  const toPath = (key: "value" | "invested") =>
    series
      .map((item, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${y(item[key]).toFixed(1)}`)
      .join(" ");
  const imoexPath = series
    .map((item, index) =>
      item.imoex == null ? null : `${index === 0 || series[index - 1]?.imoex == null ? "M" : "L"} ${x(index).toFixed(1)} ${y(item.imoex).toFixed(1)}`
    )
    .filter(Boolean)
    .join(" ");
  const areaPath = `${toPath("value")} L ${x(series.length - 1).toFixed(1)} ${y(minV).toFixed(1)} L ${x(0).toFixed(1)} ${y(minV).toFixed(1)} Z`;
  const active = series[hover ?? series.length - 1];
  const ticks = 4;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-display text-2xl">{formatMoney(active.value)}</p>
          <p className="text-xs text-moss">{formatDay(active.day)}</p>
        </div>
        <div className="flex gap-2">
          {(["1y", "all"] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setPeriod(item)}
              className={`border px-3 py-1 text-xs ${
                period === item ? "border-forest text-forest" : "border-line text-moss hover:border-forest"
              }`}
            >
              {item === "1y" ? "1 год" : "Всё"}
            </button>
          ))}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-3 h-64 w-full"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - box.left) / box.width;
          const index = Math.round(ratio * (series.length - 1));
          setHover(Math.max(0, Math.min(series.length - 1, index)));
        }}
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
        <path d={areaPath} fill="#1f4a38" opacity="0.12" />
        <path d={toPath("value")} fill="none" stroke="#1f4a38" strokeWidth="2" />
        <path d={toPath("invested")} fill="none" stroke="#3d6b54" strokeWidth="1.5" strokeDasharray="5 4" />
        {imoexPath ? <path d={imoexPath} fill="none" stroke="#9b2c2c" strokeWidth="1.5" /> : null}
        <line
          x1={x(hover ?? series.length - 1)}
          x2={x(hover ?? series.length - 1)}
          y1={pad.top}
          y2={height - pad.bottom}
          stroke="#1c1b16"
          strokeOpacity="0.25"
        />
        <text x={pad.left} y={height - 6} className="fill-moss" fontSize="10">
          {formatDay(series[0].day)}
        </text>
        <text x={width - pad.right} y={height - 6} textAnchor="end" className="fill-moss" fontSize="10">
          {formatDay(series[series.length - 1].day)}
        </text>
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-moss">
        <span>
          <span className="mr-1 inline-block h-2 w-4 bg-forest align-middle" />
          стоимость
        </span>
        <span>
          <span className="mr-1 inline-block h-0.5 w-4 border-t border-dashed border-moss align-middle" />
          вложено
        </span>
        {series.some((item) => item.imoex != null) ? (
          <span>
            <span className="mr-1 inline-block h-0.5 w-4 bg-danger align-middle" />
            IMOEX к старту периода
          </span>
        ) : null}
      </div>
    </div>
  );
}
