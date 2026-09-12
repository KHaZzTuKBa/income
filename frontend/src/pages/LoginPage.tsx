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
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md border border-line bg-paper-2/50 p-8 shadow-[8px_8px_0_0_#1f4a38]">
        <p className="font-display text-3xl">Portfel</p>
        <p className="mt-2 text-sm text-moss">Вход в личный учёт брокерского счёта</p>
        <form className="mt-8 space-y-4" onSubmit={onSubmit}>
          <label className="block text-sm">
            Логин
            <input
              className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="block text-sm">
            Пароль
            <input
              type="password"
              className="mt-1 w-full border border-line bg-paper px-3 py-2 outline-none focus:border-forest"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {mutation.isError ? (
            <p className="text-sm text-danger">
              {mutation.error instanceof Error ? mutation.error.message : "Не удалось войти"}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full bg-forest py-2.5 text-sm text-paper hover:bg-forest-2 disabled:opacity-60"
          >
            {mutation.isPending ? "Входим…" : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
}
