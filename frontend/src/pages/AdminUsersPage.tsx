import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type AdminUser,
  type BulkResult,
  type UserAction,
  type UserStatus,
  applyUserAction,
  getLegacyPortfolio,
  listUsers,
  transferLegacyPortfolio,
} from "../api/admin";
import { formatPhone, plural } from "../validation";

type Mode = "requests" | "accounts";

type Filter = {
  id: string;
  label: string;
  statuses: UserStatus[];
  actions: UserAction[];
};

const FILTERS: Record<Mode, Filter[]> = {
  requests: [
    { id: "pending", label: "Новые", statuses: ["pending"], actions: ["approve", "reject"] },
    { id: "rejected", label: "Отклонённые", statuses: ["rejected"], actions: ["approve", "delete"] },
  ],
  accounts: [
    { id: "all", label: "Все", statuses: ["active", "frozen"], actions: ["freeze", "unfreeze", "delete"] },
    { id: "active", label: "Активные", statuses: ["active"], actions: ["freeze", "delete"] },
    { id: "frozen", label: "Замороженные", statuses: ["frozen"], actions: ["unfreeze", "delete"] },
  ],
};

const ACTION_LABELS: Record<UserAction, string> = {
  approve: "Одобрить",
  reject: "Отклонить",
  freeze: "Заморозить",
  unfreeze: "Разморозить",
  delete: "Удалить",
};

const ACTION_STYLES: Record<UserAction, string> = {
  approve: "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm shadow-emerald-600/20",
  unfreeze: "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm shadow-emerald-600/20",
  reject: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
  freeze: "border border-sky-200 bg-white text-sky-700 hover:bg-sky-50",
  delete: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
};

const STATUS_BADGES: Record<UserStatus, { label: string; className: string }> = {
  pending: { label: "на рассмотрении", className: "bg-amber-50 text-amber-800 border-amber-200" },
  active: { label: "активен", className: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  frozen: { label: "заморожен", className: "bg-sky-50 text-sky-800 border-sky-200" },
  rejected: { label: "отклонена", className: "bg-red-50 text-red-700 border-red-200" },
};

const ACCOUNT_FORMS: [string, string, string] = ["аккаунт", "аккаунта", "аккаунтов"];

function formatWhen(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function SelectAll({
  checked,
  indeterminate,
  disabled,
  onChange,
}: {
  checked: boolean;
  indeterminate: boolean;
  disabled: boolean;
  onChange: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.indeterminate = indeterminate;
    }
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      className="h-4 w-4 cursor-pointer accent-emerald-600"
      checked={checked}
      disabled={disabled}
      onChange={onChange}
      aria-label="Выбрать все"
    />
  );
}

function LegacyBanner() {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<number | "">("");

  const legacy = useQuery({ queryKey: ["admin-legacy"], queryFn: getLegacyPortfolio });
  const candidates = useQuery({
    queryKey: ["admin-users", ["active"], ""],
    queryFn: () => listUsers(["active"], ""),
    enabled: legacy.data?.has_portfolio === true,
  });

  const mutation = useMutation({
    mutationFn: (userId: number) => transferLegacyPortfolio(userId),
    onSuccess: async () => {
      setTarget("");
      await queryClient.invalidateQueries({ queryKey: ["admin-legacy"] });
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });

  if (!legacy.data?.has_portfolio) {
    return null;
  }

  const options = (candidates.data?.items ?? []).filter((item) => !item.has_portfolio);
  const details = [
    legacy.data.token_hint ? `токен ••••${legacy.data.token_hint}` : null,
    legacy.data.accounts_count > 0
      ? `${legacy.data.accounts_count} ${plural(legacy.data.accounts_count, ["счёт", "счёта", "счетов"])}`
      : null,
    legacy.data.categories_count > 0
      ? `${legacy.data.categories_count} ${plural(legacy.data.categories_count, ["категория", "категории", "категорий"])}`
      : null,
  ].filter(Boolean);

  function onTransfer() {
    if (target === "") {
      return;
    }
    const user = options.find((item) => item.id === target);
    if (window.confirm(`Передать портфель администратора пользователю «${user?.username ?? target}»?`)) {
      mutation.mutate(target);
    }
  }

  return (
    <div className="rounded-3xl border border-amber-200 bg-amber-50/70 p-5 sm:p-6">
      <p className="text-sm font-semibold text-amber-900">У админского аккаунта остался портфель</p>
      <p className="mt-1 text-sm text-amber-800">
        {details.length > 0 ? `${details.join(", ")}. ` : ""}
        Администратор портфель не видит. Передайте его своему личному аккаунту: токен, история и категории
        перейдут к нему целиком.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          className="min-w-56 rounded-full border border-amber-200 bg-white px-4 py-2 text-sm text-slate-900 outline-none focus:border-amber-400 focus:ring-4 focus:ring-amber-500/10"
          value={target}
          onChange={(event) => setTarget(event.target.value ? Number(event.target.value) : "")}
        >
          <option value="">Выберите пользователя</option>
          {options.map((item) => (
            <option key={item.id} value={item.id}>
              {item.username}
              {item.email ? ` · ${item.email}` : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onTransfer}
          disabled={target === "" || mutation.isPending}
          className="rounded-full bg-amber-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:bg-amber-700 active:scale-95 disabled:opacity-50"
        >
          {mutation.isPending ? "Передаём…" : "Передать портфель"}
        </button>
        {options.length === 0 && candidates.isSuccess ? (
          <span className="text-xs text-amber-800">Нет активных пользователей без портфеля</span>
        ) : null}
      </div>
      {mutation.isError ? (
        <p className="mt-3 text-sm text-danger">
          {mutation.error instanceof Error ? mutation.error.message : "Не удалось передать портфель"}
        </p>
      ) : null}
    </div>
  );
}

export function AdminUsersPage({ mode }: { mode: Mode }) {
  const queryClient = useQueryClient();
  const filters = FILTERS[mode];
  const [filterId, setFilterId] = useState(filters[0].id);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const query = useDebounced(search, 300);
  const filter = filters.find((item) => item.id === filterId) ?? filters[0];

  const users = useQuery({
    queryKey: ["admin-users", filter.statuses, query.trim()],
    queryFn: () => listUsers(filter.statuses, query),
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    setSelected(new Set());
  }, [filterId, query]);

  const mutation = useMutation({
    mutationFn: ({ ids, action }: { ids: number[]; action: UserAction }) => applyUserAction(ids, action),
    onSuccess: async (result: BulkResult) => {
      setSelected(new Set());
      setNotice(
        result.skipped > 0
          ? `Готово: ${result.updated}. Пропущено: ${result.skipped} — действие к ним не подходит.`
          : `Готово: ${result.updated} ${plural(result.updated, ACCOUNT_FORMS)}.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      await queryClient.invalidateQueries({ queryKey: ["admin-legacy"] });
    },
    onError: () => setNotice(null),
  });

  const items: AdminUser[] = users.data?.items ?? [];
  const counts = users.data?.counts;
  const selectedIds = items.filter((item) => selected.has(item.id)).map((item) => item.id);
  const allSelected = items.length > 0 && selectedIds.length === items.length;
  const someSelected = selectedIds.length > 0 && !allSelected;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(items.map((item) => item.id)));
  }

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function run(action: UserAction) {
    if (selectedIds.length === 0) {
      return;
    }
    if (action === "delete") {
      const what = `${selectedIds.length} ${plural(selectedIds.length, ACCOUNT_FORMS)}`;
      const warning =
        mode === "accounts"
          ? `Удалить ${what}? Портфели, токены и история удалятся без возможности восстановления.`
          : `Удалить ${what} насовсем? Логин, почта и телефон освободятся.`;
      if (!window.confirm(warning)) {
        return;
      }
    }
    setNotice(null);
    mutation.mutate({ ids: selectedIds, action });
  }

  const title = mode === "requests" ? "Заявки на регистрацию" : "Пользователи";
  const description =
    mode === "requests"
      ? "Новые пользователи попадают сюда и не могут войти, пока вы не одобрите заявку."
      : "Замороженный пользователь сразу теряет доступ, данные сохраняются. Удаление стирает портфель целиком.";
  const emptyText = query.trim()
    ? "Ничего не найдено"
    : mode === "requests"
      ? filter.id === "pending"
        ? "Новых заявок нет"
        : "Отклонённых заявок нет"
      : "Пользователей пока нет";

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">{description}</p>
      </div>

      {mode === "accounts" ? <LegacyBanner /> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {filters.map((item) => {
            const amount = counts ? item.statuses.reduce((sum, status) => sum + (counts[status] ?? 0), 0) : null;
            const active = item.id === filter.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setFilterId(item.id)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-200 ${
                  active
                    ? "bg-emerald-500/10 text-emerald-800 font-semibold"
                    : "text-slate-600 hover:bg-emerald-500/5 hover:text-emerald-800"
                }`}
              >
                {item.label}
                {amount !== null ? (
                  <span className="rounded-full bg-slate-200/70 px-1.5 text-[11px] font-semibold leading-5 text-slate-700">
                    {amount}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Поиск по логину, почте, телефону"
          className="w-full sm:w-80 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all duration-200 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-sm text-slate-600">
          Выбрано: <span className="font-semibold tabular-nums text-slate-900">{selectedIds.length}</span>
        </span>
        {filter.actions.map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => run(action)}
            disabled={selectedIds.length === 0 || mutation.isPending}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-all duration-200 active:scale-95 disabled:opacity-40 disabled:active:scale-100 ${ACTION_STYLES[action]}`}
          >
            {ACTION_LABELS[action]}
          </button>
        ))}
        {notice ? <span className="text-sm text-emerald-700">{notice}</span> : null}
        {mutation.isError ? (
          <span className="text-sm text-danger">
            {mutation.error instanceof Error ? mutation.error.message : "Не удалось выполнить действие"}
          </span>
        ) : null}
      </div>

      <div className="rounded-3xl border border-slate-200/90 bg-[#F1F5F4] p-1.5 shadow-xs">
        <div className="overflow-x-auto rounded-[1.3rem]">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-[#E2EAE7] text-xs font-semibold uppercase tracking-wider text-slate-600">
              <tr>
                <th className="w-10 px-4 py-3">
                  <SelectAll
                    checked={allSelected}
                    indeterminate={someSelected}
                    disabled={items.length === 0}
                    onChange={toggleAll}
                  />
                </th>
                <th className="px-4 py-3">Логин</th>
                <th className="px-4 py-3">Почта</th>
                <th className="px-4 py-3">Телефон</th>
                <th className="px-4 py-3">Статус</th>
                {mode === "accounts" ? <th className="px-4 py-3">Портфель</th> : null}
                <th className="px-4 py-3">Заявка</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 bg-transparent text-slate-800">
              {users.isLoading ? (
                <tr>
                  <td className="px-4 py-6 text-center text-slate-500" colSpan={7}>
                    Загружаем…
                  </td>
                </tr>
              ) : users.isError ? (
                <tr>
                  <td className="px-4 py-6 text-center text-danger" colSpan={7}>
                    {users.error instanceof Error ? users.error.message : "Не удалось загрузить список"}
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-center text-slate-500" colSpan={7}>
                    {emptyText}
                  </td>
                </tr>
              ) : (
                items.map((item) => {
                  const badge = STATUS_BADGES[item.status];
                  const checked = selected.has(item.id);
                  return (
                    <tr
                      key={item.id}
                      onClick={() => toggle(item.id)}
                      className={`cursor-pointer transition-colors duration-150 ${
                        checked ? "bg-emerald-500/10" : "hover:bg-emerald-500/5"
                      }`}
                    >
                      <td className="px-4 py-3" onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          className="h-4 w-4 cursor-pointer accent-emerald-600"
                          checked={checked}
                          onChange={() => toggle(item.id)}
                          aria-label={`Выбрать ${item.username}`}
                        />
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-900">{item.username}</td>
                      <td className="px-4 py-3 text-slate-700">{item.email ?? "—"}</td>
                      <td className="px-4 py-3 whitespace-nowrap tabular-nums text-slate-700">{formatPhone(item.phone)}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${badge.className}`}>
                          {badge.label}
                        </span>
                      </td>
                      {mode === "accounts" ? (
                        <td className="px-4 py-3 text-slate-600">{item.has_portfolio ? "подключён" : "—"}</td>
                      ) : null}
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatWhen(item.created_at)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
