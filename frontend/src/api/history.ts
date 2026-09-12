import { apiJson } from "./http";

export type HistoryPeriod = "week" | "month" | "year" | "6m" | "1y" | "all" | "custom";
export type HistoryGranularity = "day" | "month";

export type HistoryPoint = {
  day: string;
  value: string;
  cash: string;
  securities: string;
  invested: string;
  imoex: string | null;
};

export type HistorySeries = {
  account_id: number | null;
  account_name: string;
  points: HistoryPoint[];
};

export type HistorySnapshot = {
  building: boolean;
  period: string;
  granularity: HistoryGranularity;
  from_day: string | null;
  to_day: string | null;
  years: number[];
  points: HistoryPoint[];
  series: HistorySeries[];
  xirr_percent: string | null;
  xirr_from: string | null;
};

export type HistoryQuery = {
  refresh?: boolean;
  period?: HistoryPeriod;
  year?: number;
  from?: string;
  to?: string;
};

export function getHistory(query: HistoryQuery = {}) {
  const params = new URLSearchParams();
  if (query.refresh) {
    params.set("refresh", "true");
  }
  if (query.period) {
    params.set("period", query.period);
  }
  if (query.year != null) {
    params.set("year", String(query.year));
  }
  if (query.from) {
    params.set("from", query.from);
  }
  if (query.to) {
    params.set("to", query.to);
  }
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiJson<HistorySnapshot>(`/api/history${suffix}`);
}
