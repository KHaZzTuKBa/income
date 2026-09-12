import { apiJson } from "./http";

export type HistoryPoint = {
  day: string;
  value: string;
  cash: string;
  securities: string;
  invested: string;
  imoex: string | null;
};

export type HistorySnapshot = {
  building: boolean;
  points: HistoryPoint[];
  xirr_percent: string | null;
  xirr_from: string | null;
};

export function getHistory(refresh = false) {
  const query = refresh ? "?refresh=true" : "";
  return apiJson<HistorySnapshot>(`/api/history${query}`);
}
