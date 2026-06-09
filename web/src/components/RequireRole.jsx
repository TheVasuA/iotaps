import { Navigate } from "react-router-dom";
import { useAppSelector } from "@/store/hooks";
import { selectRole } from "@/store/authSlice";

// Role guard: restrict a route subtree to a specific role (e.g. the Super_Admin
// admin platform, Req 23-29). Authenticated users without the required role are
// redirected to the dashboard rather than the login screen.
export default function RequireRole({ role, children }) {
  const currentRole = useAppSelector(selectRole);
  if (currentRole !== role) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}
