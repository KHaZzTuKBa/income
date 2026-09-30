import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getCalendar, type CalendarEvent, type CalendarMonth } from "../api/calendar";
import { PaymentsChart } from "../components/PaymentsChart";

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

function formatShare(value: string | null | undefined): string {
  if (value == null) {
    return "—";
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return "—";
  }
  return `${parsed.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
}

function monthTitle(month: CalendarMonth): string {
  const label = new Date(month.year, month.month - 1, 1).toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
  });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function kindLabel(kind: string): string {
  return kind === "coupon" ? "купон" : "дивиденд";
}

function statusLabel(status: string): string {
  switch (status) {
    case "received":
      return "получено";
    case "declared":
      return "объявлено";
    case "forecast":
      return "прогноз";
    default:
      return status;
  }
}

function formatDay(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU");
}

export function CalendarPage() {
  const queryClient = useQueryClient();
  const calendar = useQuery({
    queryKey: ["calendar"],
    queryFn: () => getCalendar(false),
  });
  const refreshMutation = useMutation({
    mutationFn: () => getCalendar(true),
    onSuccess: async (data) => {
      queryClient.setQueryData(["calendar"], data);
    },
  });

  const data = refreshMutation.data ?? calendar.data;
  const upcoming = (data?.events ?? []).filter((item) => item.status !== "received");
  const received = (data?.events ?? []).filter((item) => item.status === "received").reverse();

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">Календарь</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Факт — дивиденды и купоны из журнала операций. Прогноз на 12 месяцев: объявленные дивиденды
            и купоны по текущим позициям.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 text-sm font-semibold shadow-sm shadow-emerald-600/20 transition-all duration-200 active:scale-95 disabled:opacity-50"
        >
          <svg
            viewBox="0 0 16 16"
            className={`h-4 w-4 shrink-0 ${refreshMutation.isPending ? "animate-spin" : ""}`}
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
          <span>{refreshMutation.isPending ? "Обновляем…" : "Обновить прогноз"}</span>
        </button>
      </div>

      {calendar.isLoading && !data ? <p className="text-sm text-slate-500">Загружаем…</p> : null}
      {calendar.isError ? (
        <p className="text-sm text-danger">
          {calendar.error instanceof Error ? calendar.error.message : "Не удалось загрузить календарь"}
        </p>
      ) : null}
      {refreshMutation.isError ? (
        <p className="text-sm text-danger">
          {refreshMutation.error instanceof Error
            ? refreshMutation.error.message
            : "Не удалось обновить прогноз"}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Получено за 12 мес</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">{formatMoney(data?.received_12m)}</p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Прогноз на 12 мес</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">{formatMoney(data?.forecast_12m)}</p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Пассивный доход</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-emerald-700 whitespace-nowrap tabular-nums">{formatShare(data?.yield_percent)}</p>
          <p className="mt-1 text-xs text-slate-500">Прогноз / стоимость бумаг</p>
        </article>
        <article className="rounded-3xl border border-emerald-500/15 bg-white p-6 shadow-sm transition-all duration-200 hover:shadow-md hover:border-emerald-500/30">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Получено за всё время</p>
          <p className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">{formatMoney(data?.received_all_time)}</p>
        </article>
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">12 месяцев</h2>
        <div className="mt-4 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
          {(data?.months ?? []).map((month) => (
            <article key={`${month.year}-${month.month}`} className="rounded-2xl border border-emerald-500/10 bg-white p-4 shadow-xs">
              <p className="text-sm font-semibold text-slate-800">{monthTitle(month)}</p>
              <p className="mt-1.5 text-xl font-bold tracking-tight text-slate-900 whitespace-nowrap tabular-nums">{formatMoney(month.total)}</p>
              <p className="mt-1 text-xs text-slate-500">
                получено {formatMoney(month.received)} · ждать {formatMoney(month.upcoming)}
              </p>
            </article>
          ))}
        </div>
      </div>

      <PaymentsChart enabled={calendar.isSuccess} />

      <EventTable title="Ближайшие выплаты" rows={upcoming} empty="Нет объявленных и прогнозных выплат." />
      <EventTable title="Получено за 12 месяцев" rows={received} empty="В журнале нет дивидендов и купонов за этот период." />
    </section>
  );
}

function EventTable({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: CalendarEvent[];
  empty: string;
}) {
  return (
    <div>
      <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">{title}</h2>
      <div className="mt-4 rounded-3xl border border-slate-200/90 bg-[#F1F5F4] p-1.5 shadow-xs">
        <div className="overflow-x-auto rounded-[1.3rem]">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-[#E2EAE7] text-xs font-semibold uppercase tracking-wider text-slate-600">
              <tr>
                <th className="px-4 py-3">Дата</th>
                <th className="px-4 py-3">Бумага</th>
                <th className="px-4 py-3">Тип</th>
                <th className="px-4 py-3">Статус</th>
                <th className="px-4 py-3">Сумма</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/60 bg-transparent text-slate-800">
              {rows.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-center text-slate-500" colSpan={5}>
                    {empty}
                  </td>
                </tr>
              ) : (
                rows.map((item) => (
                  <tr
                    key={`${item.status}-${item.figi}-${item.event_date}-${item.kind}`}
                    className="hover:bg-emerald-500/5 transition-colors duration-150"
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatDay(item.event_date)}</td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-900">{item.ticker}</p>
                      <p className="text-xs text-slate-500">{item.name}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-full bg-slate-200/70 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                        {kindLabel(item.kind)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          item.status === "received"
                            ? "bg-emerald-100 text-emerald-800"
                            : item.status === "declared"
                              ? "bg-blue-100 text-blue-800"
                              : "bg-slate-200/80 text-slate-700"
                        }`}
                      >
                        {statusLabel(item.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold whitespace-nowrap tabular-nums text-slate-900">
                      {formatMoney(item.amount_rub)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
