import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getConnection, getSyncRuns, saveToken, startSync } from "../api/invest";

function formatWhen(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("ru-RU");
}

function statusLabel(status: string | null): string {
  switch (status) {
    case "running":
      return "идёт синхронизация";
    case "ok":
      return "готово";
    case "error":
      return "ошибка";
    case "idle":
      return "токен сохранён";
    default:
      return "нет данных";
  }
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");

  const connection = useQuery({
    queryKey: ["connection"],
    queryFn: getConnection,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });

  const runs = useQuery({
    queryKey: ["sync-runs"],
    queryFn: getSyncRuns,
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "running") ? 2000 : false,
  });

  const saveMutation = useMutation({
    mutationFn: () => saveToken(token.trim()),
    onSuccess: async (data) => {
      setToken("");
      queryClient.setQueryData(["connection"], data);
      await queryClient.invalidateQueries({ queryKey: ["connection"] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: startSync,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["connection"] });
      await queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["operations"] });
      await queryClient.invalidateQueries({ queryKey: ["sectors"] });
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    saveMutation.mutate();
  }

  const configured = connection.data?.configured === true;
  const running = connection.data?.status === "running" || syncMutation.isPending;

  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">Настройки</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Нужен read-only токен Invest API из кабинета Т‑Инвестиций. Он шифруется на сервере и в
          браузер больше не возвращается.
        </p>
      </div>

      <form className="max-w-xl space-y-4 rounded-3xl border border-emerald-500/15 bg-white p-6 sm:p-7 shadow-sm transition-all duration-200" onSubmit={onSubmit}>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Статус:</span>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-medium border ${
              connection.data?.status === "ok"
                ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                : connection.data?.status === "running"
                  ? "bg-blue-50 text-blue-800 border-blue-200"
                  : connection.data?.status === "error"
                    ? "bg-red-50 text-red-800 border-red-200"
                    : "bg-slate-100 text-slate-700 border-slate-200"
            }`}
          >
            {statusLabel(connection.data?.status ?? null)}
          </span>
          {connection.data?.token_hint ? (
            <span className="text-xs text-slate-500">· {connection.data.token_hint}</span>
          ) : null}
        </div>
        <label className="block">
          <span className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
            Токен
          </span>
          <input
            type="password"
            className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-2.5 text-sm text-slate-900 outline-none transition-all duration-200 hover:border-emerald-400/50 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            autoComplete="off"
            placeholder={configured ? "Вставьте новый токен, чтобы заменить" : "t.xxxxx"}
            required
          />
        </label>
        {saveMutation.isError ? (
          <p className="text-sm text-danger">
            {saveMutation.error instanceof Error ? saveMutation.error.message : "Не удалось сохранить"}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={saveMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2.5 text-sm font-semibold shadow-sm shadow-emerald-600/20 transition-all duration-200 active:scale-95 disabled:opacity-50 cursor-pointer"
        >
          {saveMutation.isPending ? "Проверяем…" : "Сохранить токен"}
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={() => syncMutation.mutate()}
          disabled={!configured || running}
          className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 text-sm font-semibold shadow-sm shadow-emerald-600/20 transition-all duration-200 active:scale-95 disabled:opacity-50"
        >
          <svg
            viewBox="0 0 16 16"
            className={`h-4 w-4 shrink-0 ${running ? "animate-spin" : ""}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M1.5 8a6.5 6.5 0 1 0 1.9-4.6L1.5 5.5" />
            <path d="M1.5 1.5v4h4" />
          </svg>
          <span>{running ? "Обновляем…" : "Обновить"}</span>
        </button>
        {connection.data?.history_from ? (
          <p className="text-sm text-slate-500">История операций с {connection.data.history_from}</p>
        ) : null}
        {connection.data?.last_error ? (
          <p className="text-sm text-danger">{connection.data.last_error}</p>
        ) : null}
        {syncMutation.isError ? (
          <p className="text-sm text-danger">
            {syncMutation.error instanceof Error ? syncMutation.error.message : "Не удалось запустить синк"}
          </p>
        ) : null}
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Журнал синка</h2>
        <div className="mt-4 rounded-3xl border border-slate-200/90 bg-[#F1F5F4] p-1.5 shadow-xs">
          <div className="overflow-x-auto rounded-[1.3rem]">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-[#E2EAE7] text-xs font-semibold uppercase tracking-wider text-slate-600">
                <tr>
                  <th className="px-4 py-3">Когда</th>
                  <th className="px-4 py-3">Источник</th>
                  <th className="px-4 py-3">Статус</th>
                  <th className="px-4 py-3">Счета</th>
                  <th className="px-4 py-3">Операции</th>
                  <th className="px-4 py-3">Позиции</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 bg-transparent text-slate-800">
                {(runs.data ?? []).length === 0 ? (
                  <tr>
                    <td className="px-4 py-6 text-center text-slate-500" colSpan={6}>
                      Пока пусто. Сохраните токен и нажмите «Обновить».
                    </td>
                  </tr>
                ) : (
                  (runs.data ?? []).map((run) => (
                    <tr key={run.id} className="align-top hover:bg-emerald-500/5 transition-colors duration-150">
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatWhen(run.started_at)}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-slate-200/70 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                          {run.trigger === "schedule" ? "расписание" : "вручную"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            run.status === "ok"
                              ? "bg-emerald-100 text-emerald-800"
                              : run.status === "running"
                                ? "bg-blue-100 text-blue-800"
                                : "bg-red-100 text-red-800"
                          }`}
                        >
                          {statusLabel(run.status)}
                        </span>
                        {run.error_message ? (
                          <p className="mt-1 text-xs text-danger">{run.error_message}</p>
                        ) : null}
                        {run.notes ? <p className="mt-1 whitespace-pre-wrap text-xs text-slate-500">{run.notes}</p> : null}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap tabular-nums text-slate-700">{run.accounts_count}</td>
                      <td className="px-4 py-3 whitespace-nowrap tabular-nums text-slate-700">{run.operations_count}</td>
                      <td className="px-4 py-3 whitespace-nowrap tabular-nums text-slate-700">{run.positions_count}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
