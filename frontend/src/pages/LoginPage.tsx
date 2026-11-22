import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { getMe, homePath, login } from "../api/auth";
import { AuthShell, Spinner, authButtonClass, authInputClass } from "../components/AuthShell";
import { LoadingScreen } from "../components/LoadingScreen";

export function LoginPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const reason = searchParams.get("reason");

  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
  });

  const mutation = useMutation({
    mutationFn: () => login(username, password),
    onSuccess: (loggedIn) => {
      queryClient.clear();
      queryClient.setQueryData(["me"], loggedIn);
    },
  });

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (user) {
    return <Navigate to={homePath(user)} replace />;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <AuthShell subtitle="Вход в личный учёт портфеля">
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        {reason && !mutation.isError ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-3 text-xs font-medium text-amber-800">
            {reason}
          </div>
        ) : null}
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
          Логин
          <input
            className={authInputClass}
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
            className={authInputClass}
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
        <button type="submit" disabled={mutation.isPending} className={authButtonClass}>
          {mutation.isPending ? (
            <>
              <Spinner />
              <span>Входим…</span>
            </>
          ) : (
            "Войти"
          )}
        </button>
        <p className="text-center text-sm text-slate-500">
          Нет аккаунта?{" "}
          <Link to="/register" className="font-semibold text-emerald-700 hover:text-emerald-800">
            Зарегистрироваться
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
