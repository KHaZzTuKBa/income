import { apiJson } from "./http";

export type ConnectionStatus = {
  configured: boolean;
  token_hint: string | null;
  status: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  history_from: string | null;
  accounts_count: number;
  operations_count: number;
  positions_count: number;
};

export type SyncRun = {
  id: number;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  accounts_count: number;
  operations_count: number;
  instruments_count: number;
  positions_count: number;
  error_message: string | null;
  notes: string | null;
};

export type Account = {
  id: number;
  broker_account_id: string;
  name: string;
  type: string;
  status: string;
};

export type Position = {
  account_id: number;
  account_name: string;
  figi: string;
  ticker: string;
  name: string;
  instrument_type: string;
  quantity: string;
  average_price: string;
  average_price_currency: string;
  current_price: string;
  current_price_currency: string;
};

export type Operation = {
  id: number;
  account_name: string;
  broker_operation_id: string;
  operation_type: string;
  name: string;
  figi: string;
  ticker: string;
  quantity: string;
  payment: string;
  currency: string;
  occurred_at: string;
};

export type DashboardPosition = Position & {
  value: string;
  cost: string;
  pnl: string;
  pnl_percent: string | null;
  share: string;
  is_cash: boolean;
  average_source: string;
};

export type Dashboard = {
  value: string;
  invested: string;
  profit: string;
  profit_percent: string | null;
  cash: string;
  prices_as_of: string | null;
  prices_live: boolean;
  history_from: string | null;
  invested_missing: boolean;
  positions: DashboardPosition[];
};

export function getConnection() {
  return apiJson<ConnectionStatus>("/api/settings/connection");
}

export function saveToken(token: string) {
  return apiJson<ConnectionStatus>("/api/settings/connection", {
    method: "PUT",
    body: JSON.stringify({ token }),
  });
}

export function startSync() {
  return apiJson<SyncRun>("/api/sync", { method: "POST" });
}

export function getSyncRuns() {
  return apiJson<SyncRun[]>("/api/sync/runs");
}

export function getAccounts() {
  return apiJson<Account[]>("/api/accounts");
}

export function getDashboard() {
  return apiJson<Dashboard>("/api/dashboard");
}

export function getPositions() {
  return apiJson<Position[]>("/api/positions");
}

export function getOperations() {
  return apiJson<Operation[]>("/api/operations");
}
