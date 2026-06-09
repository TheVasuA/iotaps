import { Navigate, useLocation } from "react-router-dom";
import { useAppSelector } from "@/store/hooks";
import { selectIsAuthenticated } from "@/store/authSlice";

// Route guard: redirect unauthenticated users to /login, preserving the target
// path so they return after signing in.
export default function RequireAuth({ children }) {
  const isAuthenticated = useAppSelector(selectIsAuthenticated);
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
