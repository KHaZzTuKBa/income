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
        <h1 className="font-display text-3xl">Настройки</h1>
        <p className="mt-2 max-w-2xl text-sm text-moss">
          Нужен read-only токен Invest API из кабинета Т‑Инвестиций. Он шифруется на сервере и в
          браузер больше не возвращается.
        </p>
      </div>

      <form className="max-w-xl space-y-4 border border-line bg-paper-2/40 p-5" onSubmit={onSubmit}>
        <p className="text-sm">
          Статус: {statusLabel(connection.data?.status ?? null)}
          {connection.data?.token_hint ? ` · ${connection.data.token_hint}` : ""}
        </p>
        <label className="block text-sm">
          Токен
          <input
            type="password"
            className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
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
          className="bg-forest px-4 py-2 text-sm text-paper hover:bg-forest-2 disabled:opacity-60"
        >
          {saveMutation.isPending ? "Проверяем…" : "Сохранить токен"}
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={() => syncMutation.mutate()}
          disabled={!configured || running}
          className="border border-line bg-paper px-4 py-2 text-sm hover:border-forest hover:text-forest disabled:opacity-60"
        >
          {running ? "Обновляем…" : "Обновить"}
        </button>
        {connection.data?.history_from ? (
          <p className="text-sm text-moss">История операций с {connection.data.history_from}</p>
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
        <h2 className="font-display text-2xl">Журнал синка</h2>
        <div className="mt-4 overflow-x-auto border border-line">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="bg-paper-2 text-moss">
              <tr>
                <th className="px-3 py-2 font-normal">Когда</th>
                <th className="px-3 py-2 font-normal">Источник</th>
                <th className="px-3 py-2 font-normal">Статус</th>
                <th className="px-3 py-2 font-normal">Счета</th>
                <th className="px-3 py-2 font-normal">Операции</th>
                <th className="px-3 py-2 font-normal">Позиции</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data ?? []).length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-moss" colSpan={6}>
                    Пока пусто. Сохраните токен и нажмите «Обновить».
                  </td>
                </tr>
              ) : (
                (runs.data ?? []).map((run) => (
                  <tr key={run.id} className="border-t border-line align-top">
                    <td className="px-3 py-2">{formatWhen(run.started_at)}</td>
                    <td className="px-3 py-2">{run.trigger === "schedule" ? "расписание" : "вручную"}</td>
                    <td className="px-3 py-2">
                      {statusLabel(run.status)}
                      {run.error_message ? (
                        <p className="mt-1 text-xs text-danger">{run.error_message}</p>
                      ) : null}
                      {run.notes ? <p className="mt-1 whitespace-pre-wrap text-xs text-moss">{run.notes}</p> : null}
                    </td>
                    <td className="px-3 py-2">{run.accounts_count}</td>
                    <td className="px-3 py-2">{run.operations_count}</td>
                    <td className="px-3 py-2">{run.positions_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
