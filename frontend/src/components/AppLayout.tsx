import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getMe, logout } from "../api/auth";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-200 ${
    isActive
      ? "bg-emerald-500/10 text-emerald-800 font-semibold shadow-xs"
      : "text-slate-600 hover:text-emerald-800 hover:bg-emerald-500/5"
  }`;

export function AppLayout() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: user } = useQuery({ queryKey: ["me"], queryFn: getMe });

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      queryClient.setQueryData(["me"], null);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate("/login", { replace: true });
    },
  });

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-900">
      <header className="sticky top-0 z-30 border-b border-emerald-500/10 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 text-white font-bold text-base shadow-sm shadow-emerald-500/25">
                P
              </span>
              <div>
                <p className="font-bold text-lg leading-tight tracking-tight text-slate-900">Portfel</p>
                <p className="text-[11px] font-medium text-emerald-700/80">Личный учёт портфеля</p>
              </div>
            </div>
            <nav className="flex flex-wrap items-center gap-1.5">
              <NavLink to="/" end className={linkClass}>
                Дашборд
              </NavLink>
              <NavLink to="/categories" className={linkClass}>
                Категории
              </NavLink>
              <NavLink to="/sectors" className={linkClass}>
                Отрасли
              </NavLink>
              <NavLink to="/calendar" className={linkClass}>
                Календарь
              </NavLink>
              <NavLink to="/settings" className={linkClass}>
                Настройки
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-800">
              {user?.username}
            </span>
            <button
              type="button"
              onClick={() => logoutMutation.mutate()}
              disabled={logoutMutation.isPending}
              className="rounded-full border border-emerald-500/15 bg-white/80 px-3.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-emerald-50 hover:text-emerald-800 hover:border-emerald-500/30 transition-all duration-200 disabled:opacity-60 shadow-xs"
            >
              Выйти
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
