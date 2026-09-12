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
  })} ₽`;
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

function deltaClass(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed) || Math.abs(parsed) < 0.05) {
    return "text-moss";
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
        <h1 className="font-display text-3xl">Категории</h1>
        <p className="mt-2 max-w-2xl text-sm text-moss">
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
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Портфель</p>
          <p className="mt-3 font-display text-3xl">{formatMoney(data?.portfolio_value)}</p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Цели корня</p>
          <p className="mt-3 font-display text-3xl">{data ? formatShare(data.root_target) : "—"}</p>
          <p className="mt-2 text-xs text-moss">Сумма целевых долей корневых папок</p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Без категории</p>
          <p className="mt-3 font-display text-3xl">{formatMoney(data?.unassigned_value)}</p>
          <p className="mt-2 text-xs text-moss">
            {data ? formatShare(data.unassigned_share) : "—"} стоимости
          </p>
        </article>
      </div>

      <div>
        <h2 className="font-display text-2xl">Факт vs план</h2>
        <div className="mt-3 overflow-x-auto border border-line">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="bg-paper-2 text-moss">
              <tr>
                <th className="px-3 py-2 font-normal">Папка</th>
                <th className="px-3 py-2 font-normal">Факт</th>
                <th className="px-3 py-2 font-normal">Цель</th>
                <th className="px-3 py-2 font-normal">Δ</th>
                <th className="px-3 py-2 font-normal">Стоимость</th>
              </tr>
            </thead>
            <tbody>
              {flat.length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-moss" colSpan={5}>
                    Пока нет папок. Добавьте первую ниже.
                  </td>
                </tr>
              ) : (
                flat.map(({ node, depth }) => (
                  <tr key={node.id} className="border-t border-line">
                    <td className="px-3 py-2" style={{ paddingLeft: `${0.75 + depth * 1.1}rem` }}>
                      {node.name}
                    </td>
                    <td className="px-3 py-2">
                      <ShareBar fact={node.fact_share} target={node.target_share} />
                    </td>
                    <td className="px-3 py-2">{formatShare(node.target_share)}</td>
                    <td className={`px-3 py-2 ${deltaClass(node.delta_share)}`}>
                      {Number(node.delta_share) > 0 ? "+" : ""}
                      {formatShare(node.delta_share)}
                    </td>
                    <td className="px-3 py-2">{formatMoney(node.value)}</td>
                  </tr>
                ))
              )}
              {data && Number(data.unassigned_value) > 0 ? (
                <tr className="border-t border-line">
                  <td className="px-3 py-2 text-moss">Без категории</td>
                  <td className="px-3 py-2">
                    <ShareBar fact={data.unassigned_share} target="0" />
                  </td>
                  <td className="px-3 py-2 text-moss">—</td>
                  <td className="px-3 py-2 text-moss">{formatShare(data.unassigned_share)}</td>
                  <td className="px-3 py-2">{formatMoney(data.unassigned_value)}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <form className="max-w-xl space-y-3 border border-line bg-paper-2/40 p-5" onSubmit={onCreate}>
        <h2 className="font-display text-2xl">Новая папка</h2>
        <label className="block text-sm">
          Название
          <input
            className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            Цель, %
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            />
          </label>
          <label className="block text-sm">
            Родитель
            <select
              className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
              value={parentId}
              onChange={(event) => setParentId(event.target.value)}
            >
              <option value="">Корень</option>
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
          className="bg-forest px-4 py-2 text-sm text-paper hover:bg-forest-2 disabled:opacity-60"
        >
          {createMutation.isPending ? "Добавляем…" : "Добавить папку"}
        </button>
      </form>

      <div className="space-y-4">
        <h2 className="font-display text-2xl">Папки и бумаги</h2>
        {flat.length === 0 ? (
          <p className="text-sm text-moss">Дерево пустое.</p>
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
        <h2 className="font-display text-2xl">Без категории</h2>
        <ul className="mt-3 space-y-2">
          {(data?.unassigned ?? []).length === 0 ? (
            <li className="text-sm text-moss">Все бумаги распределены по папкам.</li>
          ) : (
            (data?.unassigned ?? []).map((item) => (
              <li
                key={item.figi}
                className="flex flex-wrap items-center justify-between gap-3 border border-line bg-paper-2/30 px-4 py-3 text-sm"
              >
                <div>
                  <p>
                    {item.ticker}
                    {item.is_cash ? (
                      <span className="ml-2 text-xs uppercase tracking-wide text-moss">кэш</span>
                    ) : null}
                  </p>
                  <p className="text-xs text-moss">{item.name}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span>{formatMoney(item.value)}</span>
                  <select
                    className="border border-line bg-paper px-2 py-1 text-sm outline-none focus:border-forest"
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
                    <option value="">{flat.length === 0 ? "Сначала папка" : "В папку"}</option>
                    {flat.map(({ node, depth }) => (
                      <option key={node.id} value={node.id}>
                        {"— ".repeat(depth)}
                        {node.name}
                      </option>
                    ))}
                  </select>
                </div>
              </li>
            ))
          )}
        </ul>
      </div>
    </section>
  );
}

function ShareBar({ fact, target }: { fact: string; target: string }) {
  const factNum = Math.max(0, Number(fact) || 0);
  const targetNum = Math.max(0, Number(target) || 0);
  return (
    <div className="min-w-[8rem]">
      <div className="relative h-2 bg-paper-2">
        <div
          className="absolute inset-y-0 left-0 bg-forest"
          style={{ width: `${Math.min(factNum, 100)}%` }}
        />
        {targetNum > 0 ? (
          <span
            className="absolute top-[-3px] h-3.5 w-px bg-ink"
            style={{ left: `${Math.min(targetNum, 100)}%` }}
          />
        ) : null}
      </div>
      <p className="mt-1 text-xs text-moss">{formatShare(fact)}</p>
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
      className="space-y-3 border border-line bg-paper-2/30 p-4"
      style={{ marginLeft: `${depth * 1.25}rem` }}
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-[12rem] flex-1 text-sm">
          Название
          <input
            className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
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
          Цель, %
          <input
            type="number"
            min={0}
            max={100}
            step="0.1"
            className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
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
          className="border border-line bg-paper px-3 py-2 text-sm text-danger hover:border-danger disabled:opacity-60"
        >
          Удалить
        </button>
      </div>
      <ul className="space-y-1 text-sm">
        {node.holdings.length === 0 ? (
          <li className="text-moss">В папке пока нет бумаг.</li>
        ) : (
          node.holdings.map((item) => (
            <li key={item.figi} className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {item.ticker}
                {item.is_cash ? <span className="ml-2 text-xs text-moss">кэш</span> : null}
                <span className="text-moss"> · {formatMoney(item.value)}</span>
              </span>
              <button
                type="button"
                disabled={busy}
                className="text-xs text-moss hover:text-forest disabled:opacity-60"
                onClick={() => onAssign(item.figi, null)}
              >
                убрать
              </button>
            </li>
          ))
        )}
      </ul>
      {unassigned.length > 0 ? (
        <select
          className="border border-line bg-paper px-2 py-1 text-sm outline-none focus:border-forest"
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
          <option value="">Добавить бумагу</option>
          {unassigned.map((item) => (
            <option key={item.figi} value={item.figi}>
              {item.ticker} · {item.name}
            </option>
          ))}
        </select>
      ) : null}
    </article>
  );
}
