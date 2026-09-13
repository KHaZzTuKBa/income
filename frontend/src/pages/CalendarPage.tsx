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
  })} ₽`;
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
          <h1 className="font-display text-3xl">Календарь</h1>
          <p className="mt-2 max-w-2xl text-sm text-moss">
            Факт — дивиденды и купоны из журнала операций. Прогноз на 12 месяцев: объявленные дивиденды
            и купоны по текущим позициям.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="border border-line bg-paper px-4 py-2 text-sm hover:border-forest hover:text-forest disabled:opacity-60"
        >
          {refreshMutation.isPending ? "Обновляем…" : "Обновить прогноз"}
        </button>
      </div>

      {calendar.isLoading && !data ? <p className="text-sm text-moss">Загружаем…</p> : null}
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
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Получено за 12 мес</p>
          <p className="mt-3 font-display text-3xl">{formatMoney(data?.received_12m)}</p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Прогноз на 12 мес</p>
          <p className="mt-3 font-display text-3xl">{formatMoney(data?.forecast_12m)}</p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Пассивный доход</p>
          <p className="mt-3 font-display text-3xl">{formatShare(data?.yield_percent)}</p>
          <p className="mt-2 text-xs text-moss">Прогноз / стоимость бумаг</p>
        </article>
        <article className="border border-line bg-paper-2/40 p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-moss">Получено за всё время</p>
          <p className="mt-3 font-display text-3xl">{formatMoney(data?.received_all_time)}</p>
        </article>
      </div>

      <div>
        <h2 className="font-display text-2xl">12 месяцев</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(data?.months ?? []).map((month) => (
            <article key={`${month.year}-${month.month}`} className="border border-line bg-paper-2/30 p-4">
              <p className="text-sm">{monthTitle(month)}</p>
              <p className="mt-2 font-display text-2xl">{formatMoney(month.total)}</p>
              <p className="mt-1 text-xs text-moss">
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
      <h2 className="font-display text-2xl">{title}</h2>
      <div className="mt-3 overflow-x-auto border border-line">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <thead className="bg-paper-2 text-moss">
            <tr>
              <th className="px-3 py-2 font-normal">Дата</th>
              <th className="px-3 py-2 font-normal">Бумага</th>
              <th className="px-3 py-2 font-normal">Тип</th>
              <th className="px-3 py-2 font-normal">Статус</th>
              <th className="px-3 py-2 font-normal">Сумма</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="px-3 py-3 text-moss" colSpan={5}>
                  {empty}
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={`${item.status}-${item.figi}-${item.event_date}-${item.kind}`} className="border-t border-line">
                  <td className="px-3 py-2">{formatDay(item.event_date)}</td>
                  <td className="px-3 py-2">
                    <p>{item.ticker}</p>
                    <p className="text-xs text-moss">{item.name}</p>
                  </td>
                  <td className="px-3 py-2">{kindLabel(item.kind)}</td>
                  <td className="px-3 py-2">{statusLabel(item.status)}</td>
                  <td className="px-3 py-2">{formatMoney(item.amount_rub)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
