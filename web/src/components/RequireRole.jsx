import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectRole, setCredentials, logout } from "@/store/authSlice";
import { principalFromToken } from "@/lib/authApi";
import { tokenStore } from "@/lib/apiClient";
import { refreshAccessToken } from "@/lib/sessionRefresh";

function PageLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

// Role guard: restrict a route subtree to a specific role (e.g. super_admin).
// If the JWT is stale after a role promotion, tries one silent refresh from the DB.
export default function RequireRole({ role, children }) {
  const currentRole = useAppSelector(selectRole);
  const dispatch = useAppDispatch();
  const location = useLocation();
  const [status, setStatus] = useState("checking"); // checking | ok | denied

  useEffect(() => {
    let cancelled = false;

    async function verify() {
      if (currentRole === role) {
        setStatus("ok");
        return;
      }

      const access = tokenStore.getAccess();
      const tokenRole = access ? principalFromToken(access)?.role : null;
      if (tokenRole === role) {
        const user = principalFromToken(access);
        dispatch(
          setCredentials({
            user,
            accessToken: access,
            refreshToken: tokenStore.getRefresh(),
          })
        );
        setStatus("ok");
        return;
      }

      if (tokenStore.getRefresh()) {
        try {
          const newAccess = await refreshAccessToken();
          const user = principalFromToken(newAccess);
          if (user?.role === role) {
            dispatch(
              setCredentials({
                user,
                accessToken: newAccess,
                refreshToken: tokenStore.getRefresh(),
              })
            );
            if (!cancelled) setStatus("ok");
            return;
          }
        } catch {
          /* fall through to re-auth */
        }
      }

      tokenStore.clear();
      dispatch(logout());
      if (!cancelled) setStatus("denied");
    }

    verify();
    return () => {
      cancelled = true;
    };
  }, [currentRole, role, dispatch]);

  if (status === "checking") {
    return <PageLoader />;
  }

  if (status === "denied") {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: location.pathname,
          reauth: true,
          message: "Sign in again to open Platform admin.",
        }}
      />
    );
  }

  return children;
}
