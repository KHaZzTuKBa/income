import { type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  assignHolding,
  createCategory,
  deleteCategory,
  getCategories,
  patchCategory,
  type CategoryHolding,
  type CategoryNode,
} from "../api/categories";

function formatMoney(value: string | undefined): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return "—";
  }
  return `${parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}\u00A0₽`;
}

function formatShare(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return `${parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
}

function formatSignedMoney(value: string): string {
  const parsed = Number(value);
  const formatted = formatMoney(value);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return formatted;
  }
  return `+${formatted}`;
}

function PnlHint({ pnl, pnlPercent }: { pnl: string; pnlPercent: string | null }) {
  const costMissing = pnlPercent == null && Number(pnl) === 0;
  if (costMissing) {
    return null;
  }
  return (
    <span className={`ml-1 ${deltaClass(pnl)}`}>
      {" "}
      ({formatSignedMoney(pnl)}
      {pnlPercent != null ? ` · ${Number(pnlPercent) > 0 ? "+" : ""}${formatShare(pnlPercent)}` : ""})
    </span>
  );
}

function deltaClass(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed) || Math.abs(parsed) < 0.05) {
    return "text-slate-500";
  }
  return parsed > 0 ? "text-gain" : "text-danger";
}

function flatten(nodes: CategoryNode[], depth = 0): { node: CategoryNode; depth: number }[] {
  const rows: { node: CategoryNode; depth: number }[] = [];
  for (const node of nodes) {
    rows.push({ node, depth });
    rows.push(...flatten(node.children, depth + 1));
  }
  return rows;
}

export function CategoriesPage() {
  const queryClient = useQueryClient();
  const snapshot = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
    refetchInterval: 30_000,
  });

  const [name, setName] = useState("");
  const [target, setTarget] = useState("0");
  const [parentId, setParentId] = useState<string>("");

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["categories"] });
  };

  const createMutation = useMutation({
    mutationFn: () =>
      createCategory({
        name: name.trim(),
        parent_id: parentId ? Number(parentId) : null,
        target_share: Number(target) || 0,
      }),
    onSuccess: async () => {
      setName("");
      setTarget("0");
      setParentId("");
      await invalidate();
    },
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { name?: string; target_share?: number } }) =>
      patchCategory(id, body),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCategory,
    onSuccess: invalidate,
  });

  const assignMutation = useMutation({
    mutationFn: ({ figi, categoryId }: { figi: string; categoryId: number | null }) =>
      assignHolding(figi, categoryId),
    onSuccess: invalidate,
  });

  const data = snapshot.data;
  const flat = useMemo(() => flatten(data?.tree ?? []), [data?.tree]);

  function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    createMutation.mutate();
  }

  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">Категории</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Целевые доли считаются от стоимости всего портфеля. Факт папки включает бумаги в ней и во
          вложенных. Вложенная цель не вычитается из родительской.
        </p>
      </div>

      {snapshot.isError ? (
        <p className="text-sm text-danger">
          {snapshot.error instanceof Error ? snapshot.error.message : "Не удалось загрузить категории"}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Портфель</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">
            {formatMoney(data?.portfolio_value)}
          </p>
          <p className="mt-2 text-xs text-slate-500">Общая стоимость всех активов</p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Цели корня</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">
            {data ? formatShare(data.root_target) : "—"}
          </p>
          <p className="mt-2 text-xs text-slate-500">Сумма целевых долей корневых папок</p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Без категории</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">
            {formatMoney(data?.unassigned_value)}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            {data ? formatShare(data.unassigned_share) : "—"} от стоимости портфеля
          </p>
        </article>
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Факт vs план</h2>
        <div className="mt-4 rounded-3xl border border-slate-200/90 bg-[#F1F5F4] p-1.5 shadow-xs">
          <div className="overflow-x-auto rounded-[1.3rem]">
            <table className="w-full min-w-[48rem] text-left text-sm">
              <thead className="bg-[#E2EAE7] text-xs font-semibold uppercase tracking-wider text-slate-600">
                <tr>
                  <th className="px-4 py-3">Папка</th>
                  <th className="px-4 py-3">Факт</th>
                  <th className="px-4 py-3">Цель</th>
                  <th className="px-4 py-3">Δ</th>
                  <th className="px-4 py-3">Стоимость</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 bg-transparent text-slate-800">
                {flat.length === 0 ? (
                  <tr>
                    <td className="px-4 py-6 text-center text-slate-500" colSpan={5}>
                      Пока нет папок. Добавьте первую ниже.
                    </td>
                  </tr>
                ) : (
                  flat.map(({ node, depth }) => (
                    <tr key={node.id} className="hover:bg-emerald-500/5 transition-colors duration-150">
                      <td className="px-4 py-3 font-medium text-slate-900" style={{ paddingLeft: `${1 + depth * 1.25}rem` }}>
                        <span className="inline-flex items-center gap-2">
                          {depth > 0 ? <span className="text-slate-400">└─</span> : null}
                          {node.name}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <ShareBar fact={node.fact_share} target={node.target_share} />
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-700">{formatShare(node.target_share)}</td>
                      <td className={`px-4 py-3 font-semibold ${deltaClass(node.delta_share)}`}>
                        {Number(node.delta_share) > 0 ? "+" : ""}
                        {formatShare(node.delta_share)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap tabular-nums font-medium text-slate-900">
                        {formatMoney(node.value)}
                        <PnlHint pnl={node.pnl} pnlPercent={node.pnl_percent} />
                      </td>
                    </tr>
                  ))
                )}
                {data && Number(data.unassigned_value) > 0 ? (
                  <tr className="hover:bg-emerald-500/5 transition-colors duration-150 font-medium text-slate-600">
                    <td className="px-4 py-3 text-slate-500">Без категории</td>
                    <td className="px-4 py-3">
                      <ShareBar fact={data.unassigned_share} target="0" />
                    </td>
                    <td className="px-4 py-3 text-slate-400">—</td>
                    <td className="px-4 py-3 text-slate-500">{formatShare(data.unassigned_share)}</td>
                    <td className="px-4 py-3 whitespace-nowrap tabular-nums text-slate-900">
                      {formatMoney(data.unassigned_value)}
                      <PnlHint pnl={data.unassigned_pnl} pnlPercent={data.unassigned_pnl_percent} />
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <form className="max-w-xl space-y-4 rounded-3xl border border-emerald-500/15 bg-white p-6 sm:p-7 shadow-sm transition-all duration-200" onSubmit={onCreate}>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Новая папка</h2>
        <label className="block">
          <span className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
            Название
          </span>
          <input
            className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
            placeholder="Например, Акции РФ или Дивидендные"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
              Цель, %
            </span>
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-2.5 text-sm text-slate-900 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
              Родитель
            </span>
            <select
              className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-2.5 text-sm text-slate-900 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10 cursor-pointer"
              value={parentId}
              onChange={(event) => setParentId(event.target.value)}
            >
              <option value="">Корень (без родителя)</option>
              {flat.map(({ node, depth }) => (
                <option key={node.id} value={node.id}>
                  {"— ".repeat(depth)}
                  {node.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {createMutation.isError ? (
          <p className="text-sm text-danger">
            {createMutation.error instanceof Error ? createMutation.error.message : "Не удалось создать"}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2.5 text-sm font-semibold shadow-sm shadow-emerald-600/20 transition-all duration-200 active:scale-95 disabled:opacity-50 cursor-pointer"
        >
          {createMutation.isPending ? "Добавляем…" : "Добавить папку"}
        </button>
      </form>

      <div className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Папки и бумаги</h2>
        {flat.length === 0 ? (
          <p className="text-sm text-slate-500">Дерево пустое.</p>
        ) : (
          flat.map(({ node, depth }) => (
            <CategoryEditor
              key={node.id}
              node={node}
              depth={depth}
              unassigned={data?.unassigned ?? []}
              busy={patchMutation.isPending || deleteMutation.isPending || assignMutation.isPending}
              onSaveName={(value) => patchMutation.mutate({ id: node.id, body: { name: value } })}
              onSaveTarget={(value) =>
                patchMutation.mutate({ id: node.id, body: { target_share: value } })
              }
              onDelete={() => {
                if (window.confirm(`Удалить «${node.name}» и вложенные папки?`)) {
                  deleteMutation.mutate(node.id);
                }
              }}
              onAssign={(figi, categoryId) => assignMutation.mutate({ figi, categoryId })}
            />
          ))
        )}
        {patchMutation.isError ? (
          <p className="text-sm text-danger">
            {patchMutation.error instanceof Error ? patchMutation.error.message : "Не удалось сохранить"}
          </p>
        ) : null}
        {deleteMutation.isError ? (
          <p className="text-sm text-danger">
            {deleteMutation.error instanceof Error ? deleteMutation.error.message : "Не удалось удалить"}
          </p>
        ) : null}
        {assignMutation.isError ? (
          <p className="text-sm text-danger">
            {assignMutation.error instanceof Error
              ? assignMutation.error.message
              : "Не удалось назначить бумагу"}
          </p>
        ) : null}
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Без категории</h2>
        <div className="mt-4 rounded-3xl border border-slate-200/80 bg-white p-5 sm:p-6 shadow-xs">
          {(data?.unassigned ?? []).length === 0 ? (
            <p className="text-sm text-slate-500">Все бумаги распределены по папкам.</p>
          ) : (
            <ul className="space-y-2.5">
              {(data?.unassigned ?? []).map((item) => (
                <li
                  key={item.figi}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-[#F8FAFA] px-4 py-3 text-sm transition-colors hover:bg-emerald-50/40 hover:border-emerald-200/50"
                >
                  <div>
                    <p className="font-semibold text-slate-900">
                      {item.ticker}
                      {item.is_cash ? (
                        <span className="ml-2 rounded-full bg-slate-200/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                          кэш
                        </span>
                      ) : null}
                    </p>
                    <p className="text-xs text-slate-500">{item.name}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-semibold whitespace-nowrap tabular-nums text-slate-900">{formatMoney(item.value)}</span>
                    <select
                      className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800 outline-none hover:border-emerald-400/50 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/10 cursor-pointer disabled:opacity-50"
                      defaultValue=""
                      disabled={assignMutation.isPending || flat.length === 0}
                      onChange={(event) => {
                        const value = event.target.value;
                        if (!value) {
                          return;
                        }
                        assignMutation.mutate({ figi: item.figi, categoryId: Number(value) });
                        event.target.value = "";
                      }}
                    >
                      <option value="">{flat.length === 0 ? "Сначала папка" : "В папку…"}</option>
                      {flat.map(({ node, depth }) => (
                        <option key={node.id} value={node.id}>
                          {"— ".repeat(depth)}
                          {node.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

function ShareBar({ fact, target }: { fact: string; target: string }) {
  const factNum = Math.max(0, Number(fact) || 0);
  const targetNum = Math.max(0, Number(target) || 0);
  return (
    <div className="min-w-[8rem] max-w-[12rem]">
      <div className="relative h-2.5 rounded-full bg-slate-200/80 overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-emerald-600 transition-all duration-300"
          style={{ width: `${Math.min(factNum, 100)}%` }}
        />
        {targetNum > 0 ? (
          <span
            className="absolute top-0 bottom-0 w-0.5 bg-slate-900 z-10"
            style={{ left: `${Math.min(targetNum, 100)}%` }}
            title={`Цель: ${targetNum}%`}
          />
        ) : null}
      </div>
      <p className="mt-1 text-xs font-medium text-slate-500">{formatShare(fact)}</p>
    </div>
  );
}

function CategoryEditor({
  node,
  depth,
  unassigned,
  busy,
  onSaveName,
  onSaveTarget,
  onDelete,
  onAssign,
}: {
  node: CategoryNode;
  depth: number;
  unassigned: CategoryHolding[];
  busy: boolean;
  onSaveName: (name: string) => void;
  onSaveTarget: (target: number) => void;
  onDelete: () => void;
  onAssign: (figi: string, categoryId: number | null) => void;
}) {
  const [name, setName] = useState(node.name);
  const [target, setTarget] = useState(String(Number(node.target_share)));

  return (
    <article
      className="space-y-4 rounded-3xl border border-slate-200/80 bg-white p-5 sm:p-6 shadow-xs transition-all duration-200 hover:border-emerald-500/20 hover:shadow-sm"
      style={{ marginLeft: `${depth * 1.5}rem` }}
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-[12rem] flex-1 text-sm">
          <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
            Название папки
          </span>
          <input
            className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-3.5 py-2 text-sm text-slate-900 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => {
              if (name.trim() && name.trim() !== node.name) {
                onSaveName(name.trim());
              }
            }}
          />
        </label>
        <label className="w-28 text-sm">
          <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
            Цель, %
          </span>
          <input
            type="number"
            min={0}
            max={100}
            step="0.1"
            className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-3.5 py-2 text-sm text-slate-900 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            onBlur={() => {
              const parsed = Number(target);
              if (!Number.isNaN(parsed) && parsed !== Number(node.target_share)) {
                onSaveTarget(parsed);
              }
            }}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          className="rounded-full border border-red-200 bg-red-50/70 px-4 py-2 text-sm font-semibold text-red-600 transition-all duration-200 hover:bg-red-100 hover:border-red-300 active:scale-95 disabled:opacity-50 cursor-pointer"
        >
          Удалить
        </button>
      </div>

      <div className="border-t border-slate-100 pt-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Бумаги в папке ({node.holdings.length})
        </p>
        <ul className="space-y-1.5 text-sm">
          {node.holdings.length === 0 ? (
            <li className="text-slate-400 italic text-xs py-1">В папке пока нет бумаг.</li>
          ) : (
            node.holdings.map((item) => (
              <li
                key={item.figi}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50/80 px-3 py-2 transition-colors hover:bg-emerald-50/40"
              >
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800">{item.ticker}</span>
                  {item.is_cash ? (
                    <span className="rounded-full bg-slate-200/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                      кэш
                    </span>
                  ) : null}
                  <span className="text-slate-500">· {formatMoney(item.value)}</span>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-medium text-slate-500 hover:border-red-200 hover:bg-red-50 hover:text-red-600 transition-all duration-150 disabled:opacity-50 cursor-pointer"
                  onClick={() => onAssign(item.figi, null)}
                >
                  убрать
                </button>
              </li>
            ))
          )}
        </ul>
      </div>

      {unassigned.length > 0 ? (
        <div className="pt-1">
          <select
            className="w-full max-w-sm rounded-2xl border border-slate-200 bg-slate-50/60 px-3.5 py-2 text-sm text-slate-800 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10 cursor-pointer"
            defaultValue=""
            disabled={busy}
            onChange={(event) => {
              const value = event.target.value;
              if (!value) {
                return;
              }
              onAssign(value, node.id);
              event.target.value = "";
            }}
          >
            <option value="">+ Добавить бумагу в папку</option>
            {unassigned.map((item) => (
              <option key={item.figi} value={item.figi}>
                {item.ticker} · {item.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
    </article>
  );
}
