import { Navigate, useLocation } from "react-router-dom";
import ConsoleFeatureScreen from "@/components/console/ConsoleFeatureScreen";
import { CONSOLE_FEATURES_BY_PATH } from "@/lib/consoleFeatures";

export default function ConsoleFeaturePage() {
  const { pathname } = useLocation();
  const feature = CONSOLE_FEATURES_BY_PATH[pathname];
  if (!feature) return <Navigate to="/get-started" replace />;
  return <ConsoleFeatureScreen {...feature} />;
}
