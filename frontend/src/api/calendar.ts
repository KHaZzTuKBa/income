import { apiJson } from "./http";

export type CalendarEvent = {
  figi: string;
  ticker: string;
  name: string;
  kind: string;
  status: string;
  event_date: string;
  amount: string;
  currency: string;
  amount_rub: string;
  quantity: string;
};

export type CalendarMonth = {
  year: number;
  month: number;
  received: string;
  upcoming: string;
  total: string;
};

export type CalendarSnapshot = {
  received_12m: string;
  received_all_time: string;
  forecast_12m: string;
  securities_value: string;
  yield_percent: string | null;
  forecasts_as_of: string | null;
  months: CalendarMonth[];
  events: CalendarEvent[];
};

export type PaymentPeriod = "week" | "month" | "year" | "6m" | "1y" | "all" | "custom";
export type PaymentGranularity = "day" | "month";

export type PaymentHistoryPoint = {
  day: string;
  amount: string;
};

export type PaymentHistorySnapshot = {
  period: string;
  granularity: PaymentGranularity;
  from_day: string | null;
  to_day: string | null;
  years: number[];
  total: string;
  points: PaymentHistoryPoint[];
};

export type PaymentHistoryQuery = {
  period?: PaymentPeriod;
  year?: number;
  from?: string;
  to?: string;
};

export function getCalendar(refresh = false) {
  const query = refresh ? "?refresh=true" : "";
  return apiJson<CalendarSnapshot>(`/api/calendar${query}`);
}

export function getCalendarPayments(query: PaymentHistoryQuery = {}) {
  const params = new URLSearchParams();
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
  return apiJson<PaymentHistorySnapshot>(`/api/calendar/payments${suffix}`);
}
