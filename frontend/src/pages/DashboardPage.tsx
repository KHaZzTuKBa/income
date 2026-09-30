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
  const formatted = parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${formatted}\u00A0₽`;
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
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">Портфель</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
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
        ) : (
          <Link
            to="/settings"
            className="inline-flex items-center gap-2 rounded-full bg-emerald-700 hover:bg-emerald-800 text-white px-5 py-2.5 text-sm font-semibold shadow-sm transition-all duration-200 active:scale-95"
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
        <p className="text-sm text-slate-500">
          Вводы в журнале не найдены — карточка «Вложено» может быть неполной.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Стоимость</p>
          <p className="mt-2 text-xl sm:text-2xl xl:text-[1.65rem] font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">
            {configured ? formatMoney(snapshot?.value) : "—"}
          </p>
          <p className="mt-2 text-xs text-slate-500 truncate" title={configured && snapshot ? `в т.ч. кэш ${formatMoney(snapshot.cash)}` : undefined}>
            {configured && snapshot
              ? `в т.ч. кэш ${formatMoney(snapshot.cash)}${
                  snapshot.prices_live ? " · живые цены" : " · цена с последнего синка"
                }`
              : "Позиции × цена + кэш"}
          </p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Вложено</p>
          <p className="mt-2 text-xl sm:text-2xl xl:text-[1.65rem] font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">
            {configured ? formatMoney(snapshot?.invested) : "—"}
          </p>
          <p className="mt-2 text-xs text-slate-500">Чистые вводы − выводы</p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Прибыль</p>
          <p className={`mt-2 text-xl sm:text-2xl xl:text-[1.65rem] font-extrabold tracking-tight whitespace-nowrap tabular-nums ${configured && snapshot ? moneyClass(snapshot.profit) : ""}`}>
            {configured && snapshot ? formatSignedMoney(snapshot.profit) : "—"}
          </p>
          <p className={`mt-2 text-xs ${configured ? moneyClass(snapshot?.profit) : "text-slate-500"}`}>
            {configured && snapshot?.profit_percent != null
              ? `${Number(snapshot.profit_percent) > 0 ? "+" : ""}${formatNumber(snapshot.profit_percent)}% · стоимость − вложено`
              : "Стоимость − вложено"}
          </p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">XIRR</p>
          <p className={`mt-2 text-xl sm:text-2xl xl:text-[1.65rem] font-extrabold tracking-tight whitespace-nowrap tabular-nums ${configured && snapshot?.xirr_percent ? moneyClass(snapshot.xirr_percent) : ""}`}>
            {configured && snapshot?.xirr_percent != null
              ? `${Number(snapshot.xirr_percent) > 0 ? "+" : ""}${formatNumber(snapshot.xirr_percent)}%`
              : "—"}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            {configured && snapshot?.xirr_from
              ? `годовых с ${snapshot.xirr_from}`
              : "По вводам, выводам и текущей стоимости"}
          </p>
        </article>
      </div>

      {configured ? <PortfolioCharts enabled={configured} /> : null}

      {configured ? (
        <p className="text-sm font-medium text-slate-500">
          Счетов: {connection.data?.accounts_count ?? 0} · операций:{" "}
          {connection.data?.operations_count ?? 0} · позиций: {snapshot?.positions.length ?? 0}
        </p>
      ) : null}

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Счета</h2>
        <ul className="mt-3 space-y-2">
          {(accounts.data ?? []).length === 0 ? (
            <li className="text-sm text-slate-500">Пока нет счетов.</li>
          ) : (
            (accounts.data ?? []).map((account) => (
              <li key={account.id} className="rounded-2xl border border-emerald-500/10 bg-white px-4 py-3 text-sm shadow-xs flex items-center justify-between">
                <span className="font-semibold text-slate-900">{account.name || account.broker_account_id}</span>
                <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
                  {accountType(account.type)} · {account.status === "open" ? "открыт" : account.status}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Активы</h2>
        <div className="mt-3 overflow-hidden rounded-3xl border border-slate-200/90 bg-[#F1F5F4] p-1.5 shadow-[0_4px_24px_-4px_rgba(16,185,129,0.06),0_2px_8px_-2px_rgba(0,0,0,0.02)]">
          <div className="overflow-x-auto rounded-[1.3rem]">
            <table className="w-full min-w-[56rem] text-left text-sm">
              <thead className="bg-[#E2EAE7] text-slate-700 font-semibold text-xs tracking-wider uppercase">
                <tr>
                  <th className="px-4 py-3 font-semibold">Бумага</th>
                  <th className="px-4 py-3 font-semibold">Счёт</th>
                  <th className="px-4 py-3 font-semibold">Кол-во</th>
                  <th className="px-4 py-3 font-semibold">Средняя</th>
                  <th className="px-4 py-3 font-semibold">Цена</th>
                  <th className="px-4 py-3 font-semibold">Стоимость</th>
                  <th className="px-4 py-3 font-semibold">P&amp;L</th>
                  <th className="px-4 py-3 font-semibold">Доля</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60">
                {(snapshot?.positions ?? []).length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-slate-500" colSpan={8}>
                      Нет позиций. Запустите синхронизацию.
                    </td>
                  </tr>
                ) : (
                  (snapshot?.positions ?? []).map((position) => (
                    <tr key={`${position.account_id}-${position.figi}`} className="hover:bg-white/85 transition-colors">
                      <td className="px-4 py-3">
                        <p className="font-semibold text-slate-900">
                          {position.ticker || position.figi}
                          {position.is_cash ? (
                            <span className="ml-2 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-800">кэш</span>
                          ) : null}
                        </p>
                        <p className="text-xs text-slate-500">{position.name}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{position.account_name}</td>
                      <td className="px-4 py-3 font-mono font-medium text-slate-800">{formatNumber(position.quantity)}</td>
                      <td className="px-4 py-3 font-mono text-slate-700">
                        {formatNumber(position.average_price)} {position.average_price_currency}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-700">
                        {formatNumber(position.current_price)} {position.current_price_currency}
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-900 whitespace-nowrap">{formatMoney(position.value)}</td>
                      <td className={`px-4 py-3 font-semibold whitespace-nowrap ${moneyClass(position.pnl)}`}>
                        {formatSignedMoney(position.pnl)}
                        {position.pnl_percent != null ? (
                          <span className="block text-xs font-normal">
                            {Number(position.pnl_percent) > 0 ? "+" : ""}
                            {formatNumber(position.pnl_percent)}%
                          </span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-700">{formatNumber(position.share)}%</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">Последние операции</h2>
        <div className="mt-3 overflow-hidden rounded-3xl border border-slate-200/90 bg-[#F1F5F4] p-1.5 shadow-[0_4px_24px_-4px_rgba(16,185,129,0.06),0_2px_8px_-2px_rgba(0,0,0,0.02)]">
          <div className="overflow-x-auto rounded-[1.3rem]">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <thead className="bg-[#E2EAE7] text-slate-700 font-semibold text-xs tracking-wider uppercase">
                <tr>
                  <th className="px-4 py-3 font-semibold">Дата</th>
                  <th className="px-4 py-3 font-semibold">Тип</th>
                  <th className="px-4 py-3 font-semibold">Бумага</th>
                  <th className="px-4 py-3 font-semibold">Счёт</th>
                  <th className="px-4 py-3 font-semibold">Сумма</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60">
                {(operations.data ?? []).length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-slate-500" colSpan={5}>
                      Журнал пуст.
                    </td>
                  </tr>
                ) : (
                  (operations.data ?? []).map((operation) => (
                    <tr key={operation.id} className="hover:bg-white/85 transition-colors">
                      <td className="px-4 py-3 text-slate-600 text-xs whitespace-nowrap">
                        {new Date(operation.occurred_at).toLocaleString("ru-RU")}
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-900">{operation.name || operationLabel(operation.operation_type)}</td>
                      <td className="px-4 py-3 text-slate-700">{operation.ticker || operation.figi || "—"}</td>
                      <td className="px-4 py-3 text-slate-600">{operation.account_name}</td>
                      <td className="px-4 py-3 font-semibold text-slate-900 font-mono whitespace-nowrap">
                        {formatNumber(operation.payment)} {operation.currency}
                      </td>
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
