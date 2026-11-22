import { apiJson } from "./http";

export type User = {
  id: number;
  username: string;
  is_admin: boolean;
  email: string | null;
  phone: string | null;
};

export type RegisterBody = {
  username: string;
  email: string;
  phone: string;
  password: string;
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

export function homePath(user: User): string {
  return user.is_admin ? "/admin/requests" : "/";
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

export function register(body: RegisterBody) {
  return apiJson<{ status: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function changePassword(currentPassword: string, newPassword: string) {
  return apiJson<void>("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
