const cards = [
  { title: "Стоимость", hint: "Позиции × цена + кэш" },
  { title: "Вложено", hint: "Чистые вводы − выводы" },
  { title: "Прибыль", hint: "Стоимость − вложено" },
];

export function DashboardPage() {
  return (
    <section>
      <h1 className="font-display text-3xl">Портфель</h1>
      <p className="mt-2 max-w-2xl text-sm text-moss">
        Данные появятся после синхронизации с Т‑Инвестициями. Пока это оболочка: вход, сессия и
        рабочий стол.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <article key={card.title} className="border border-line bg-paper-2/40 p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-moss">{card.title}</p>
            <p className="mt-3 font-display text-3xl">—</p>
            <p className="mt-2 text-xs text-moss">{card.hint}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
