import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "react-router-dom";
import { getMe } from "../api/auth";
import { LoadingScreen } from "./LoadingScreen";

export function RequireAuth() {
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

  return <Outlet />;
}
