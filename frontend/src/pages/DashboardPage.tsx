import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  getAccounts,
  getConnection,
  getOperations,
  getPositions,
  startSync,
} from "../api/invest";

const cards = [
  { title: "Стоимость", hint: "Позиции × цена + кэш" },
  { title: "Вложено", hint: "Чистые вводы − выводы" },
  { title: "Прибыль", hint: "Стоимость − вложено" },
];

function formatNumber(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return parsed.toLocaleString("ru-RU", { maximumFractionDigits: 6 });
}

function accountType(type: string): string {
  switch (type) {
    case "iis":
      return "ИИС";
    case "invest_box":
      return "Инвесткопилка";
    case "broker":
      return "Брокерский";
    default:
      return type;
  }
}

function operationLabel(type: string): string {
  return type.replace(/^OPERATION_TYPE_/, "").toLowerCase();
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const connection = useQuery({
    queryKey: ["connection"],
    queryFn: getConnection,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: getAccounts });
  const positions = useQuery({ queryKey: ["positions"], queryFn: getPositions });
  const operations = useQuery({ queryKey: ["operations"], queryFn: getOperations });

  const syncMutation = useMutation({
    mutationFn: startSync,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["connection"] });
      await queryClient.invalidateQueries({ queryKey: ["accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["positions"] });
      await queryClient.invalidateQueries({ queryKey: ["operations"] });
      await queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    },
  });

  const configured = connection.data?.configured === true;
  const running = connection.data?.status === "running" || syncMutation.isPending;

  useEffect(() => {
    if (connection.data?.status === "ok") {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
      void queryClient.invalidateQueries({ queryKey: ["operations"] });
    }
  }, [connection.data?.last_sync_at, connection.data?.status, queryClient]);

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl">Портфель</h1>
          <p className="mt-2 max-w-2xl text-sm text-moss">
            {configured
              ? connection.data?.history_from
                ? `Журнал операций с ${connection.data.history_from}. Стоимость и прибыль появятся в следующем блоке.`
                : "Токен сохранён. Нажмите «Обновить», чтобы подтянуть счета и операции."
              : "Сначала сохраните read-only токен Т‑Инвестиций в настройках."}
          </p>
        </div>
        {configured ? (
          <button
            type="button"
            onClick={() => syncMutation.mutate()}
            disabled={running}
            className="border border-line bg-paper px-4 py-2 text-sm hover:border-forest hover:text-forest disabled:opacity-60"
          >
            {running ? "Обновляем…" : "Обновить"}
          </button>
        ) : (
          <Link
            to="/settings"
            className="bg-forest px-4 py-2 text-sm text-paper hover:bg-forest-2"
          >
            Открыть настройки
          </Link>
        )}
      </div>

      {connection.data?.last_error ? (
        <p className="text-sm text-danger">{connection.data.last_error}</p>
      ) : null}
      {syncMutation.isError ? (
        <p className="text-sm text-danger">
          {syncMutation.error instanceof Error ? syncMutation.error.message : "Не удалось обновить"}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <article key={card.title} className="border border-line bg-paper-2/40 p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-moss">{card.title}</p>
            <p className="mt-3 font-display text-3xl">—</p>
            <p className="mt-2 text-xs text-moss">{card.hint}</p>
          </article>
        ))}
      </div>

      {configured ? (
        <p className="text-sm text-moss">
          Счетов: {connection.data?.accounts_count ?? 0} · операций:{" "}
          {connection.data?.operations_count ?? 0} · позиций: {connection.data?.positions_count ?? 0}
        </p>
      ) : null}

      <div>
        <h2 className="font-display text-2xl">Счета</h2>
        <ul className="mt-3 space-y-2">
          {(accounts.data ?? []).length === 0 ? (
            <li className="text-sm text-moss">Пока нет счетов.</li>
          ) : (
            (accounts.data ?? []).map((account) => (
              <li key={account.id} className="border border-line bg-paper-2/30 px-4 py-3 text-sm">
                <span className="font-medium">{account.name || account.broker_account_id}</span>
                <span className="text-moss">
                  {" "}
                  · {accountType(account.type)} · {account.status === "open" ? "открыт" : account.status}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>

      <div>
        <h2 className="font-display text-2xl">Позиции</h2>
        <div className="mt-3 overflow-x-auto border border-line">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-paper-2 text-moss">
              <tr>
                <th className="px-3 py-2 font-normal">Бумага</th>
                <th className="px-3 py-2 font-normal">Счёт</th>
                <th className="px-3 py-2 font-normal">Кол-во</th>
                <th className="px-3 py-2 font-normal">Средняя</th>
                <th className="px-3 py-2 font-normal">Цена</th>
              </tr>
            </thead>
            <tbody>
              {(positions.data ?? []).length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-moss" colSpan={5}>
                    Нет позиций. Запустите синхронизацию.
                  </td>
                </tr>
              ) : (
                (positions.data ?? []).map((position) => (
                  <tr key={`${position.account_id}-${position.figi}`} className="border-t border-line">
                    <td className="px-3 py-2">
                      <p>{position.ticker || position.figi}</p>
                      <p className="text-xs text-moss">{position.name}</p>
                    </td>
                    <td className="px-3 py-2">{position.account_name}</td>
                    <td className="px-3 py-2">{formatNumber(position.quantity)}</td>
                    <td className="px-3 py-2">
                      {formatNumber(position.average_price)} {position.average_price_currency}
                    </td>
                    <td className="px-3 py-2">
                      {formatNumber(position.current_price)} {position.current_price_currency}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h2 className="font-display text-2xl">Последние операции</h2>
        <div className="mt-3 overflow-x-auto border border-line">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-paper-2 text-moss">
              <tr>
                <th className="px-3 py-2 font-normal">Дата</th>
                <th className="px-3 py-2 font-normal">Тип</th>
                <th className="px-3 py-2 font-normal">Бумага</th>
                <th className="px-3 py-2 font-normal">Счёт</th>
                <th className="px-3 py-2 font-normal">Сумма</th>
              </tr>
            </thead>
            <tbody>
              {(operations.data ?? []).length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-moss" colSpan={5}>
                    Журнал пуст.
                  </td>
                </tr>
              ) : (
                (operations.data ?? []).map((operation) => (
                  <tr key={operation.id} className="border-t border-line">
                    <td className="px-3 py-2">
                      {new Date(operation.occurred_at).toLocaleString("ru-RU")}
                    </td>
                    <td className="px-3 py-2">{operation.name || operationLabel(operation.operation_type)}</td>
                    <td className="px-3 py-2">{operation.ticker || operation.figi || "—"}</td>
                    <td className="px-3 py-2">{operation.account_name}</td>
                    <td className="px-3 py-2">
                      {formatNumber(operation.payment)} {operation.currency}
                    </td>
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
