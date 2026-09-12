import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getMe, logout } from "../api/auth";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm ${isActive ? "text-forest border-b border-forest" : "text-moss hover:text-forest"}`;

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
    <div className="min-h-screen bg-paper">
      <header className="border-b border-line bg-paper-2/60">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-forest font-display text-sm text-paper">
                P
              </span>
              <div>
                <p className="font-display text-lg leading-none tracking-wide">Portfel</p>
                <p className="mt-1 text-xs text-moss">Личный учёт портфеля</p>
              </div>
            </div>
            <nav className="flex gap-4">
              <NavLink to="/" end className={linkClass}>
                Дашборд
              </NavLink>
              <NavLink to="/categories" className={linkClass}>
                Категории
              </NavLink>
              <NavLink to="/calendar" className={linkClass}>
                Календарь
              </NavLink>
              <NavLink to="/settings" className={linkClass}>
                Настройки
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-moss">{user?.username}</span>
            <button
              type="button"
              onClick={() => logoutMutation.mutate()}
              disabled={logoutMutation.isPending}
              className="border border-line bg-paper px-3 py-1.5 text-sm hover:border-forest hover:text-forest disabled:opacity-60"
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
