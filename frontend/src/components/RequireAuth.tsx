import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "react-router-dom";
import { getMe, homePath } from "../api/auth";
import { LoadingScreen } from "./LoadingScreen";

export function RequireAuth({ role }: { role: "user" | "admin" }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
  });

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (isError || !data) {
    return <Navigate to="/login" replace />;
  }

  if (data.is_admin !== (role === "admin")) {
    return <Navigate to={homePath(data)} replace />;
  }

  return <Outlet />;
}
