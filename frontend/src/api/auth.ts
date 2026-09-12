export type User = {
  id: number;
  username: string;
};

async function parseError(response: Response, fallback: string): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    if (typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    // ignore non-JSON bodies
  }
  return fallback;
}

export async function getMe(): Promise<User | null> {
  const response = await fetch("/api/auth/me", { credentials: "include" });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await parseError(response, "Не удалось загрузить профиль"));
  }
  return response.json() as Promise<User>;
}

export async function login(username: string, password: string): Promise<User> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Не удалось войти"));
  }
  return response.json() as Promise<User>;
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(await parseError(response, "Не удалось выйти"));
  }
}
