import { apiJson } from "./http";

export type UserStatus = "pending" | "active" | "frozen" | "rejected";
export type UserAction = "approve" | "reject" | "freeze" | "unfreeze" | "delete";

export type AdminUser = {
  id: number;
  username: string;
  email: string | null;
  phone: string | null;
  status: UserStatus;
  created_at: string;
  reviewed_at: string | null;
  has_portfolio: boolean;
};

export type AdminUsers = {
  items: AdminUser[];
  counts: Record<UserStatus, number>;
};

export type BulkResult = {
  updated: number;
  skipped: number;
};

export type LegacyPortfolio = {
  has_portfolio: boolean;
  token_hint: string | null;
  accounts_count: number;
  categories_count: number;
};

export function listUsers(statuses: UserStatus[], q: string) {
  const params = new URLSearchParams();
  for (const status of statuses) {
    params.append("status", status);
  }
  if (q.trim()) {
    params.set("q", q.trim());
  }
  return apiJson<AdminUsers>(`/api/admin/users?${params.toString()}`);
}

export function applyUserAction(ids: number[], action: UserAction) {
  return apiJson<BulkResult>("/api/admin/users/actions", {
    method: "POST",
    body: JSON.stringify({ ids, action }),
  });
}

export function getLegacyPortfolio() {
  return apiJson<LegacyPortfolio>("/api/admin/legacy-portfolio");
}

export function transferLegacyPortfolio(userId: number) {
  return apiJson<void>("/api/admin/legacy-portfolio/transfer", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}
