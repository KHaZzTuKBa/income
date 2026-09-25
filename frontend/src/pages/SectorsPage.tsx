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
      className="relative inline-grid grid-cols-2 border border-line bg-paper-2 p-1 text-sm"
    >
      <span
        className="pointer-events-none absolute top-1 bottom-1 left-1 w-[calc(50%-0.25rem)] bg-forest transition-transform duration-200 ease-out"
        style={{ transform: mode === "categories" ? "translateX(100%)" : "translateX(0)" }}
      />
      <button
        type="button"
        role="tab"
        aria-selected={mode === "accounts"}
        className={`relative z-10 px-5 py-1.5 ${mode === "accounts" ? "text-paper" : "text-moss"}`}
        onClick={() => onChange("accounts")}
      >
        По счетам
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "categories"}
        className={`relative z-10 px-5 py-1.5 ${mode === "categories" ? "text-paper" : "text-moss"}`}
        onClick={() => onChange("categories")}
      >
        По категориям
      </button>
    </div>
  );
}

export function SectorsPage() {
  const [mode, setMode] = useState<"accounts" | "categories">("accounts");
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

  const nothingSelected = selected.size === 0;
  const papersMissing = (sectors.data?.holdings.length ?? 0) === 0;
  const allUnknown =
    !papersMissing && (sectors.data?.holdings ?? []).every((item) => !item.sector);

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl">Отрасли</h1>
          <p className="mt-2 max-w-2xl text-sm text-moss">
            {configured
              ? "Доли по сектору экономики среди бумаг, без кэша. Сектор подтягивается при синхронизации."
              : "Сначала сохраните read-only токен Т‑Инвестиций в настройках."}
          </p>
        </div>
        {configured ? null : (
          <Link to="/settings" className="bg-forest px-4 py-2 text-sm text-paper hover:bg-forest-2">
            Открыть настройки
          </Link>
        )}
      </div>

      {configured ? <ModeSlider mode={mode} onChange={setMode} /> : null}

      {!configured ? null : sectors.isLoading ? (
        <p className="text-sm text-moss">Считаем доли…</p>
      ) : sectors.isError ? (
        <p className="text-sm text-danger">
          {sectors.error instanceof Error ? sectors.error.message : "Не удалось загрузить отрасли"}
        </p>
      ) : papersMissing ? (
        <p className="text-sm text-moss">Нет бумаг в позициях. Обновите портфель на дашборде.</p>
      ) : (
        <>
          {allUnknown ? (
            <p className="text-sm text-moss">
              У бумаг ещё нет отрасли — нажмите «Обновить» на дашборде, чтобы подтянуть сектор из Т‑Банка.
            </p>
          ) : null}

          {mode === "accounts" ? (
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
          ) : (
            <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
              <div className="h-fit border border-line bg-paper-2/40 p-5 lg:sticky lg:top-6">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-display text-lg">Папки</h2>
                  <div className="flex gap-2 text-xs">
                    <button
                      type="button"
                      className="text-moss hover:text-forest"
                      onClick={() => setPicked(folderKeys)}
                    >
                      Все
                    </button>
                    <button
                      type="button"
                      className="text-moss hover:text-forest"
                      onClick={() => setPicked([])}
                    >
                      Снять
                    </button>
                  </div>
                </div>
                {categories.isLoading ? (
                  <p className="mt-4 text-sm text-moss">Загружаем категории…</p>
                ) : (
                  <ul className="mt-4 space-y-2 text-sm">
                    {folderRows.map(({ node, depth }) => (
                      <li key={node.id} style={{ paddingLeft: depth * 12 }}>
                        <label className="flex cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={selected.has(String(node.id))}
                            onChange={() => toggleFolder(String(node.id))}
                          />
                          <span className="truncate">{node.name}</span>
                        </label>
                      </li>
                    ))}
                    <li>
                      <label className="flex cursor-pointer items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selected.has(UNASSIGNED)}
                          onChange={() => toggleFolder(UNASSIGNED)}
                        />
                        <span>Без категории</span>
                      </label>
                    </li>
                  </ul>
                )}
              </div>
              <div className="space-y-6">
                {nothingSelected ? (
                  <p className="text-sm text-moss">Отметьте папки, чтобы собрать диаграммы.</p>
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
          )}
        </>
      )}
    </section>
  );
}
