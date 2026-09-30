import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { getMe, login } from "../api/auth";
import { LoadingScreen } from "../components/LoadingScreen";

export function LoginPage() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
  });

  const mutation = useMutation({
    mutationFn: () => login(username, password),
    onSuccess: (loggedIn) => {
      queryClient.setQueryData(["me"], loggedIn);
    },
  });

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-[#f8faf9] px-4">
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(ellipse_80%_80%_at_50%_-10%,rgba(16,185,129,0.08),rgba(255,255,255,0))]" />
      <div className="w-full max-w-md rounded-3xl border border-emerald-500/15 bg-white/95 p-8 sm:p-10 shadow-[0_12px_40px_-6px_rgba(16,185,129,0.08),0_4px_16px_-2px_rgba(0,0,0,0.02)] backdrop-blur-md">
        <div className="flex flex-col items-center text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 text-white font-bold text-xl shadow-md shadow-emerald-600/30 mb-3">
            P
          </span>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Portfel</h1>
          <p className="mt-1 text-sm text-slate-500">Вход в личный учёт портфеля</p>
        </div>

        <form className="mt-8 space-y-4" onSubmit={onSubmit}>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
            Логин
            <input
              className="mt-1.5 w-full rounded-2xl border border-slate-200 bg-slate-50/50 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all duration-200 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
            Пароль
            <input
              type="password"
              className="mt-1.5 w-full rounded-2xl border border-slate-200 bg-slate-50/50 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all duration-200 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-500/10"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {mutation.isError ? (
            <div className="rounded-2xl border border-red-200 bg-red-50/80 p-3 text-xs font-medium text-red-700">
              {mutation.error instanceof Error ? mutation.error.message : "Не удалось войти"}
            </div>
          ) : null}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full inline-flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-white py-3 text-sm font-semibold shadow-sm shadow-emerald-600/25 transition-all duration-200 active:scale-[0.99] disabled:opacity-60"
          >
            {mutation.isPending ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                <span>Входим…</span>
              </>
            ) : (
              "Войти"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
