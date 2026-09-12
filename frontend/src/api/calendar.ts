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
  forecast_12m: string;
  securities_value: string;
  yield_percent: string | null;
  forecasts_as_of: string | null;
  months: CalendarMonth[];
  events: CalendarEvent[];
};

export function getCalendar(refresh = false) {
  const query = refresh ? "?refresh=true" : "";
  return apiJson<CalendarSnapshot>(`/api/calendar${query}`);
}
