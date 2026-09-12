import { apiJson } from "./http";

export type CategoryHolding = {
  figi: string;
  ticker: string;
  name: string;
  value: string;
  is_cash: boolean;
};

export type CategoryNode = {
  id: number;
  parent_id: number | null;
  name: string;
  target_share: string;
  sort_order: number;
  value: string;
  own_value: string;
  fact_share: string;
  delta_share: string;
  holdings: CategoryHolding[];
  children: CategoryNode[];
};

export type CategoriesSnapshot = {
  tree: CategoryNode[];
  unassigned: CategoryHolding[];
  portfolio_value: string;
  root_target: string;
  unassigned_value: string;
  unassigned_share: string;
};

export function getCategories() {
  return apiJson<CategoriesSnapshot>("/api/categories");
}

export function createCategory(body: {
  name: string;
  parent_id?: number | null;
  target_share?: number;
}) {
  return apiJson<{ id: number; name: string; parent_id: number | null }>("/api/categories", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchCategory(
  id: number,
  body: {
    name?: string;
    parent_id?: number | null;
    target_share?: number;
    sort_order?: number;
  },
) {
  return apiJson<{ id: number; name: string; parent_id: number | null }>(`/api/categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteCategory(id: number) {
  return apiJson<void>(`/api/categories/${id}`, { method: "DELETE" });
}

export function assignHolding(figi: string, categoryId: number | null) {
  return apiJson<void>("/api/categories/assignments", {
    method: "PUT",
    body: JSON.stringify({ figi, category_id: categoryId }),
  });
}
