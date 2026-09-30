import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getCategories, type CategoryHolding, type CategoryNode } from "../api/categories";
import { getConnection } from "../api/invest";
import { getSectors, type SectorHolding, type SectorSlice } from "../api/sectors";
import { SectorPie, sectorColors, type PieSlice } from "../components/SectorPie";

const UNASSIGNED = "unassigned";

function flatten(nodes: CategoryNode[], depth = 0): { node: CategoryNode; depth: number }[] {
  const rows: { node: CategoryNode; depth: number }[] = [];
  for (const node of nodes) {
    rows.push({ node, depth });
    rows.push(...flatten(node.children, depth + 1));
  }
  return rows;
}

function paperFigis(holdings: CategoryHolding[]): Set<string> {
  return new Set(holdings.filter((item) => !item.is_cash).map((item) => item.figi));
}

function aggregateHoldings(holdings: SectorHolding[], figis: Set<string>): { total: string; slices: PieSlice[] } {
  const totals = new Map<
    string,
    { label: string; value: number; papers: Map<string, { ticker: string; name: string; value: number }> }
  >();
  let total = 0;
  for (const item of holdings) {
    if (!figis.has(item.figi)) {
      continue;
    }
    const amount = Number(item.value) || 0;
    total += amount;
    const current = totals.get(item.sector) ?? {
      label: item.sector_label,
      value: 0,
      papers: new Map(),
    };
    current.value += amount;
    const paper = current.papers.get(item.figi);
    if (paper) {
      paper.value += amount;
    } else {
      current.papers.set(item.figi, { ticker: item.ticker, name: item.name, value: amount });
    }
    totals.set(item.sector, current);
  }
  const slices: SectorSlice[] = [...totals.entries()]
    .map(([key, item]) => {
      const papers = [...item.papers.entries()]
        .map(([figi, paper]) => ({
          figi,
          ticker: paper.ticker,
          name: paper.name,
          value: paper.value.toFixed(2),
          share: total > 0 ? ((paper.value / total) * 100).toFixed(2) : "0.00",
        }))
        .sort((left, right) => Number(right.value) - Number(left.value));
      return {
        key,
        label: item.label,
        value: item.value.toFixed(2),
        share: total > 0 ? ((item.value / total) * 100).toFixed(2) : "0.00",
        holdings_count: papers.length,
        holdings: papers,
      };
    })
    .sort((left, right) => {
      if (!left.key && right.key) {
        return 1;
      }
      if (left.key && !right.key) {
        return -1;
      }
      return Number(right.value) - Number(left.value);
    });
  return { total: total.toFixed(2), slices };
}

function ModeSlider({
  mode,
  onChange,
}: {
  mode: "accounts" | "categories";
  onChange: (mode: "accounts" | "categories") => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Режим отраслей"
      className="inline-flex items-center gap-1 rounded-full border border-emerald-500/15 bg-emerald-500/[0.06] p-1.5 backdrop-blur-sm shadow-xs"
    >
      <button
        type="button"
        role="tab"
        aria-selected={mode === "accounts"}
        className={`rounded-full px-5 py-2 text-sm font-semibold transition-all duration-200 ${
          mode === "accounts"
            ? "bg-white text-emerald-950 shadow-sm"
            : "text-slate-600 hover:text-emerald-900"
        }`}
        onClick={() => onChange("accounts")}
      >
        По счетам
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "categories"}
        className={`rounded-full px-5 py-2 text-sm font-semibold transition-all duration-200 ${
          mode === "categories"
            ? "bg-white text-emerald-950 shadow-sm"
            : "text-slate-600 hover:text-emerald-900"
        }`}
        onClick={() => onChange("categories")}
      >
        По категориям
      </button>
    </div>
  );
}

export function SectorsPage() {
  const [mode, setMode] = useState<"accounts" | "categories">("accounts");
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [picked, setPicked] = useState<string[] | null>(null);

  const connection = useQuery({
    queryKey: ["connection"],
    queryFn: getConnection,
  });
  const configured = connection.data?.configured === true;
  const sectors = useQuery({
    queryKey: ["sectors"],
    queryFn: getSectors,
    enabled: configured,
    refetchInterval: 30_000,
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
    enabled: configured,
    refetchInterval: 30_000,
  });

  const folderRows = useMemo(
    () => flatten(categories.data?.tree ?? []),
    [categories.data?.tree],
  );
  const folderKeys = useMemo(
    () => [...folderRows.map(({ node }) => String(node.id)), UNASSIGNED],
    [folderRows],
  );
  const selected = useMemo(() => new Set(picked ?? folderKeys), [picked, folderKeys]);

  const folderPies = useMemo(() => {
    const holdings = sectors.data?.holdings ?? [];
    const rows: { key: string; title: string; total: string; slices: PieSlice[] }[] = [];
    for (const { node } of folderRows) {
      if (!selected.has(String(node.id))) {
        continue;
      }
      const pie = aggregateHoldings(holdings, paperFigis(node.holdings));
      rows.push({ key: String(node.id), title: node.name, ...pie });
    }
    if (selected.has(UNASSIGNED)) {
      const pie = aggregateHoldings(holdings, paperFigis(categories.data?.unassigned ?? []));
      rows.push({ key: UNASSIGNED, title: "Без категории", ...pie });
    }
    return rows;
  }, [categories.data?.unassigned, folderRows, sectors.data?.holdings, selected]);

  const categoryPie = useMemo(() => {
    const figis = new Set<string>();
    for (const { node } of folderRows) {
      if (!selected.has(String(node.id))) {
        continue;
      }
      for (const figi of paperFigis(node.holdings)) {
        figis.add(figi);
      }
    }
    if (selected.has(UNASSIGNED)) {
      for (const figi of paperFigis(categories.data?.unassigned ?? [])) {
        figis.add(figi);
      }
    }
    return aggregateHoldings(sectors.data?.holdings ?? [], figis);
  }, [categories.data?.unassigned, folderRows, sectors.data?.holdings, selected]);

  const colorKeys = useMemo(() => {
    const keys = [
      ...(sectors.data?.pies ?? []).flatMap((pie) => pie.slices.map((slice) => slice.key)),
      ...folderPies.flatMap((pie) => pie.slices.map((slice) => slice.key)),
      ...categoryPie.slices.map((slice) => slice.key),
    ];
    return sectorColors(keys);
  }, [categoryPie.slices, folderPies, sectors.data?.pies]);

  const toggleFolder = (key: string) => {
    setPicked((current) => {
      const next = new Set(current ?? folderKeys);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return [...next];
    });
  };

  const changeMode = (nextMode: "accounts" | "categories") => {
    if (nextMode === mode) return;
    setIsTransitioning(true);
    setMode(nextMode);
    setTimeout(() => {
      setIsTransitioning(false);
    }, 360);
  };

  const nothingSelected = selected.size === 0;
  const papersMissing = (sectors.data?.holdings.length ?? 0) === 0;
  const allUnknown =
    !papersMissing && (sectors.data?.holdings ?? []).every((item) => !item.sector);

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3.5 py-1 text-xs font-semibold text-emerald-800 mb-2.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 animate-pulse" />
            <span>Аналитика структуры</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">Отрасли</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            {configured
              ? "Доли по сектору экономики среди бумаг, без кэша. Сектор подтягивается при синхронизации."
              : "Сначала сохраните read-only токен Т‑Инвестиций в настройках."}
          </p>
        </div>
        {configured ? null : (
          <Link
            to="/settings"
            className="inline-flex items-center gap-2 rounded-full bg-emerald-700 hover:bg-emerald-800 text-white px-5 py-2.5 text-sm font-semibold shadow-sm transition-all"
          >
            Открыть настройки
          </Link>
        )}
      </div>

      {configured ? <ModeSlider mode={mode} onChange={changeMode} /> : null}

      {!configured ? null : sectors.isLoading ? (
        <div className="rounded-3xl border border-emerald-500/15 bg-white/80 p-8 text-center backdrop-blur-sm shadow-xs">
          <div className="inline-flex h-9 w-9 animate-spin items-center justify-center rounded-full border-2 border-emerald-600 border-t-transparent" />
          <p className="mt-3 text-sm font-medium text-emerald-900">Считаем доли отраслей…</p>
        </div>
      ) : sectors.isError ? (
        <div className="rounded-3xl border border-red-200 bg-red-50/80 p-6 text-sm font-medium text-red-700">
          {sectors.error instanceof Error ? sectors.error.message : "Не удалось загрузить отрасли"}
        </div>
      ) : papersMissing ? (
        <div className="rounded-3xl border border-emerald-500/15 bg-white/80 p-8 text-center backdrop-blur-sm shadow-xs">
          <p className="text-sm font-medium text-slate-600">Нет бумаг в позициях. Обновите портфель на дашборде.</p>
        </div>
      ) : (
        <>
          {allUnknown ? (
            <div className="rounded-2xl border border-amber-500/20 bg-amber-50/80 p-4 text-sm font-medium text-amber-900">
              У бумаг ещё нет отрасли — нажмите «Обновить» на дашборде, чтобы подтянуть сектор из Т‑Банка.
            </div>
          ) : null}

          {/* Smooth swipe track between "accounts" and "categories" */}
          <div className="w-full overflow-hidden">
            <div
              className="flex w-[200%] items-start"
              style={{
                transform: mode === "categories" ? "translateX(-50%)" : "translateX(0%)",
                transition: "transform 350ms cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            >
              {/* Accounts view (Panel 1) */}
              <div
                className={`w-1/2 shrink-0 transition-opacity duration-300 ${
                  mode === "accounts"
                    ? "opacity-100"
                    : isTransitioning
                      ? "opacity-25 pointer-events-none"
                      : "h-0 max-h-0 overflow-hidden opacity-0 pointer-events-none"
                }`}
              >
                <div className="space-y-6">
                  {(sectors.data?.pies ?? []).map((pie) => (
                    <SectorPie
                      key={pie.key}
                      title={pie.label}
                      total={pie.total}
                      slices={pie.slices}
                      colors={colorKeys}
                      emptyHint="На этом счёте нет бумаг."
                    />
                  ))}
                </div>
              </div>

              {/* Categories view (Panel 2) */}
              <div
                className={`w-1/2 shrink-0 transition-opacity duration-300 ${
                  mode === "categories"
                    ? "opacity-100"
                    : isTransitioning
                      ? "opacity-25 pointer-events-none"
                      : "h-0 max-h-0 overflow-hidden opacity-0 pointer-events-none"
                }`}
              >
                <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
                  <div className="h-fit rounded-3xl border border-emerald-500/15 bg-white/90 p-5 shadow-sm backdrop-blur-md lg:sticky lg:top-24">
                    <div className="flex items-center justify-between gap-2 border-b border-emerald-500/10 pb-3.5">
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-emerald-500" />
                        <h2 className="text-base font-bold text-slate-900">Папки</h2>
                      </div>
                      <div className="flex gap-1.5 text-xs">
                        <button
                          type="button"
                          className="rounded-full bg-emerald-500/10 px-2.5 py-1 font-semibold text-emerald-800 hover:bg-emerald-500/20 transition-colors"
                          onClick={() => setPicked(folderKeys)}
                        >
                          Все
                        </button>
                        <button
                          type="button"
                          className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-200 transition-colors"
                          onClick={() => setPicked([])}
                        >
                          Снять
                        </button>
                      </div>
                    </div>
                    {categories.isLoading ? (
                      <div className="mt-4 flex items-center gap-2 text-sm text-emerald-800/80">
                        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-ping" />
                        <span>Загружаем категории…</span>
                      </div>
                    ) : (
                      <ul className="mt-3.5 space-y-1 text-sm">
                        {folderRows.map(({ node, depth }) => (
                          <li key={node.id} style={{ paddingLeft: depth * 12 }}>
                            <label className="flex cursor-pointer items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-slate-700 hover:bg-emerald-500/5 hover:text-emerald-950 transition-colors">
                              <input
                                type="checkbox"
                                className="h-4 w-4 rounded-md border-slate-300 text-emerald-600 accent-emerald-600 focus:ring-emerald-500/20"
                                checked={selected.has(String(node.id))}
                                onChange={() => toggleFolder(String(node.id))}
                              />
                              <span className="truncate font-medium">{node.name}</span>
                            </label>
                          </li>
                        ))}
                        <li>
                          <label className="flex cursor-pointer items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-slate-700 hover:bg-emerald-500/5 hover:text-emerald-950 transition-colors">
                            <input
                              type="checkbox"
                              className="h-4 w-4 rounded-md border-slate-300 text-emerald-600 accent-emerald-600 focus:ring-emerald-500/20"
                              checked={selected.has(UNASSIGNED)}
                              onChange={() => toggleFolder(UNASSIGNED)}
                            />
                            <span className="font-medium text-slate-500">Без категории</span>
                          </label>
                        </li>
                      </ul>
                    )}
                  </div>
                  <div className="space-y-6">
                    {nothingSelected ? (
                      <div className="rounded-3xl border border-emerald-500/15 bg-white/80 p-8 text-center backdrop-blur-sm shadow-xs">
                        <p className="text-sm font-medium text-slate-600">Отметьте папки, чтобы собрать диаграммы.</p>
                      </div>
                    ) : (
                      <>
                        {folderPies.map((pie) => (
                          <SectorPie
                            key={pie.key}
                            title={pie.title}
                            total={pie.total}
                            slices={pie.slices}
                            colors={colorKeys}
                            emptyHint="В этой папке нет бумаг."
                          />
                        ))}
                        <SectorPie
                          title="Все выбранные"
                          total={categoryPie.total}
                          slices={categoryPie.slices}
                          colors={colorKeys}
                          emptyHint="В выбранных папках нет бумаг."
                        />
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
