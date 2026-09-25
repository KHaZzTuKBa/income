import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getAccounts, getConnection, getDashboard, getOperations, startSync } from "../api/invest";
import { PortfolioCharts } from "../components/PortfolioChart";

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

function formatNumber(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return parsed.toLocaleString("ru-RU", { maximumFractionDigits: 6 });
}

function formatSignedMoney(value: string): string {
  const parsed = Number(value);
  const formatted = formatMoney(value);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return formatted;
  }
  return `+${formatted}`;
}

function moneyClass(value: string | null | undefined): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed) || parsed === 0) {
    return "";
  }
  return parsed > 0 ? "text-gain" : "text-danger";
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
  const configured = connection.data?.configured === true;
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    enabled: configured,
    refetchInterval: 30_000,
  });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: getAccounts, enabled: configured });
  const operations = useQuery({
    queryKey: ["operations"],
    queryFn: getOperations,
    enabled: configured,
  });
  const syncMutation = useMutation({
    mutationFn: startSync,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["connection"] });
      await queryClient.invalidateQueries({ queryKey: ["accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["operations"] });
      await queryClient.invalidateQueries({ queryKey: ["history"] });
      await queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["sectors"] });
    },
  });

  const running = connection.data?.status === "running" || syncMutation.isPending;

  useEffect(() => {
    if (connection.data?.status === "ok") {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["operations"] });
      void queryClient.invalidateQueries({ queryKey: ["history"] });
      void queryClient.invalidateQueries({ queryKey: ["sectors"] });
    }
  }, [connection.data?.last_sync_at, connection.data?.status, queryClient]);

  const snapshot = dashboard.data;
  const historyFrom = connection.data?.history_from ?? snapshot?.history_from;

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl">Портфель</h1>
          <p className="mt-2 max-w-2xl text-sm text-moss">
            {configured
              ? historyFrom
                ? `Журнал операций с ${historyFrom}. Стоимость в рублях; вложено — чистые вводы минус выводы.`
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
      {snapshot?.invested_missing ? (
        <p className="text-sm text-moss">
          Вводы в журнале не найдены — карточка «Вложено» может быть неполной.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Стоимость</p>
          <p className="mt-3 font-display text-3xl">
            {configured ? formatMoney(snapshot?.value) : "—"}
          </p>
          <p className="mt-2 text-xs text-moss">
            {configured && snapshot
              ? `в т.ч. кэш ${formatMoney(snapshot.cash)}${
                  snapshot.prices_live ? " · живые цены" : " · цена с последнего синка"
                }`
              : "Позиции × цена + кэш"}
          </p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Вложено</p>
          <p className="mt-3 font-display text-3xl">
            {configured ? formatMoney(snapshot?.invested) : "—"}
          </p>
          <p className="mt-2 text-xs text-moss">Чистые вводы − выводы</p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Прибыль</p>
          <p className={`mt-3 font-display text-3xl ${configured && snapshot ? moneyClass(snapshot.profit) : ""}`}>
            {configured && snapshot ? formatSignedMoney(snapshot.profit) : "—"}
          </p>
          <p className={`mt-2 text-xs ${configured ? moneyClass(snapshot?.profit) : "text-moss"}`}>
            {configured && snapshot?.profit_percent != null
              ? `${Number(snapshot.profit_percent) > 0 ? "+" : ""}${formatNumber(snapshot.profit_percent)}% · стоимость − вложено`
              : "Стоимость − вложено"}
          </p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">XIRR</p>
          <p className={`mt-3 font-display text-3xl ${configured && snapshot?.xirr_percent ? moneyClass(snapshot.xirr_percent) : ""}`}>
            {configured && snapshot?.xirr_percent != null
              ? `${Number(snapshot.xirr_percent) > 0 ? "+" : ""}${formatNumber(snapshot.xirr_percent)}%`
              : "—"}
          </p>
          <p className="mt-2 text-xs text-moss">
            {configured && snapshot?.xirr_from
              ? `годовых с ${snapshot.xirr_from}`
              : "По вводам, выводам и текущей стоимости"}
          </p>
        </article>
      </div>

      {configured ? <PortfolioCharts enabled={configured} /> : null}

      {configured ? (
        <p className="text-sm text-moss">
          Счетов: {connection.data?.accounts_count ?? 0} · операций:{" "}
          {connection.data?.operations_count ?? 0} · позиций: {snapshot?.positions.length ?? 0}
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
        <h2 className="font-display text-2xl">Активы</h2>
        <div className="mt-3 overflow-x-auto border border-line">
          <table className="w-full min-w-[56rem] text-left text-sm">
            <thead className="bg-paper-2 text-moss">
              <tr>
                <th className="px-3 py-2 font-normal">Бумага</th>
                <th className="px-3 py-2 font-normal">Счёт</th>
                <th className="px-3 py-2 font-normal">Кол-во</th>
                <th className="px-3 py-2 font-normal">Средняя</th>
                <th className="px-3 py-2 font-normal">Цена</th>
                <th className="px-3 py-2 font-normal">Стоимость</th>
                <th className="px-3 py-2 font-normal">P&amp;L</th>
                <th className="px-3 py-2 font-normal">Доля</th>
              </tr>
            </thead>
            <tbody>
              {(snapshot?.positions ?? []).length === 0 ? (
                <tr>
                  <td className="px-3 py-3 text-moss" colSpan={8}>
                    Нет позиций. Запустите синхронизацию.
                  </td>
                </tr>
              ) : (
                (snapshot?.positions ?? []).map((position) => (
                  <tr key={`${position.account_id}-${position.figi}`} className="border-t border-line">
                    <td className="px-3 py-2">
                      <p>
                        {position.ticker || position.figi}
                        {position.is_cash ? (
                          <span className="ml-2 text-xs uppercase tracking-wide text-moss">кэш</span>
                        ) : null}
                      </p>
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
                    <td className="px-3 py-2">{formatMoney(position.value)}</td>
                    <td className={`px-3 py-2 ${moneyClass(position.pnl)}`}>
                      {formatSignedMoney(position.pnl)}
                      {position.pnl_percent != null ? (
                        <span className="block text-xs">
                          {Number(position.pnl_percent) > 0 ? "+" : ""}
                          {formatNumber(position.pnl_percent)}%
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">{formatNumber(position.share)}%</td>
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
