import { apiJson } from "./http";

export type SectorPaper = {
  figi: string;
  ticker: string;
  name: string;
  value: string;
  share: string;
};

export type SectorSlice = {
  key: string;
  label: string;
  value: string;
  share: string;
  holdings_count: number;
  holdings: SectorPaper[];
};

export type SectorPie = {
  key: string;
  account_id: number | null;
  label: string;
  total: string;
  slices: SectorSlice[];
};

export type SectorHolding = {
  figi: string;
  ticker: string;
  name: string;
  sector: string;
  sector_label: string;
  value: string;
};

export type SectorsSnapshot = {
  pies: SectorPie[];
  holdings: SectorHolding[];
};

export function getSectors() {
  return apiJson<SectorsSnapshot>("/api/sectors");
}
