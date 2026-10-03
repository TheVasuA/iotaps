import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import RequireAuth from "@/components/RequireAuth";
import RequireRole from "@/components/RequireRole";

// Lightweight loading spinner
function PageLoader() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

// Lazy wrapper
function L(importFn) {
  const Component = lazy(importFn);
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

// Layouts are lazily-loaded modules referenced directly at the route level;
// every page resolves through L(() => import(...)) in the route table below.
const PublicLayout = lazy(() => import("@/components/public/PublicLayout"));

// AppLayout pulls in WhatsNewPopup (framer-motion), so keeping it out of the
// entry graph keeps vendor-motion off the critical path.
const AppLayout = lazy(() => import("@/components/AppLayout"));

// AdminLayout is wrapped in RequireRole + Suspense at the route level, so it
// cannot go through the L() helper and is declared here.
const AdminLayout = lazy(() => import("@/pages/admin/AdminLayout"));

export const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <Suspense fallback={<PageLoader />}>
        <PublicLayout />
      </Suspense>
    ),
    children: [
      { index: true, element: L(() => import("@/pages/public/LandingPage")) },
      { path: "pricing", element: L(() => import("@/pages/public/PricingPage")) },
      { path: "about", element: L(() => import("@/pages/public/AboutPage")) },
      { path: "contact", element: L(() => import("@/pages/public/ContactPage")) },
      { path: "docs", element: L(() => import("@/pages/public/DocsPage")) },
      { path: "terms", element: L(() => import("@/pages/public/TermsPage")) },
      { path: "privacy", element: L(() => import("@/pages/public/PrivacyPage")) },
      { path: "refund-policy", element: L(() => import("@/pages/public/RefundPolicyPage")) },
      { path: "status", element: L(() => import("@/pages/public/StatusPage")) },
      { path: "faq", element: L(() => import("@/pages/public/FaqPage")) },
      { path: "changelog", element: L(() => import("@/pages/public/ChangelogPage")) },
      { path: "platform", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.PlatformOverviewPage }))) },
      { path: "solutions", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.SolutionsHubPage }))) },
      { path: "solutions/industrial-iot", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.IndustrialIotPage }))) },
      { path: "solutions/smart-agriculture", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.SmartAgriculturePage }))) },
      { path: "solutions/energy-hvac", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.EnergyHvacPage }))) },
      { path: "blynk-alternative", element: L(() => import("@/pages/public/BlynkAlternativePage")) },
      { path: "enterprise", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.EnterprisePage }))) },
      { path: "developers", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.DevelopersHubPage }))) },
      { path: "developers/mqtt-devices", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.MqttDevicesPage }))) },
      { path: "developers/dashboards-api", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.DashboardsApiPage }))) },
      { path: "partners", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.PartnersPage }))) },
      { path: "blog", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.BlogPage }))) },
      { path: "case-studies", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.CaseStudiesPage }))) },
      { path: "security", element: L(() => import("@/pages/public/marketing/marketingPages").then((m) => ({ default: m.SecurityContactPage }))) },
      // Catch-all lives inside PublicLayout so a mistyped URL still gets the
      // site header, footer, and navigation instead of a bare unstyled div.
      { path: "*", element: L(() => import("@/pages/public/NotFoundPage")) },
    ],
  },
  { path: "/login", element: L(() => import("@/pages/auth/LoginPage")) },
  { path: "/register", element: L(() => import("@/pages/auth/RegisterPage")) },
  { path: "/forgot-password", element: L(() => import("@/pages/auth/ForgotPasswordPage")) },
  { path: "/reset-password", element: L(() => import("@/pages/auth/ResetPasswordPage")) },
  {
    element: (
      <RequireAuth>
        <Suspense fallback={<PageLoader />}>
          <AppLayout />
        </Suspense>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/get-started" replace /> },
      {
        path: "get-started",
        handle: { consoleHome: true },
        element: L(() => import("@/pages/console/GetStartedPage")),
      },
      { path: "dashboard", handle: { fullBleed: true }, element: L(() => import("@/pages/dashboards/DashboardPage")) },
      { path: "homepage", handle: { fullBleed: true }, element: L(() => import("@/pages/dashboards/DashboardPage")) },
      { path: "devices", element: L(() => import("@/pages/devices/DeviceListPage")) },
      { path: "devices/:id", element: L(() => import("@/pages/devices/DeviceDetailPage")) },
      { path: "flasher", element: L(() => import("@/pages/devices/WebFlasherPage")) },
      { path: "explorer", handle: { fullBleed: true }, element: L(() => import("@/pages/devices/MqttExplorerPage")) },
      { path: "custom-data", handle: { fullBleed: true }, element: L(() => import("@/pages/console/ConsoleFeaturePage")) },
      { path: "locations", handle: { fullBleed: true }, element: L(() => import("@/pages/console/ConsoleFeaturePage")) },
      { path: "organizations", handle: { fullBleed: true }, element: L(() => import("@/pages/console/ConsoleFeaturePage")) },
      { path: "snapshots", handle: { fullBleed: true }, element: L(() => import("@/pages/console/ConsoleFeaturePage")) },
      { path: "fleet", handle: { fullBleed: true }, element: L(() => import("@/pages/console/ConsoleFeaturePage")) },
      { path: "rules", element: L(() => import("@/pages/rules/RuleListPage")) },
      { path: "rules/:id", handle: { fullBleed: true }, element: L(() => import("@/pages/rules/RuleEditorPage")) },
      { path: "billing", element: L(() => import("@/pages/billing/BillingPage")) },
      { path: "referrals", element: L(() => import("@/pages/referrals/ReferralPage")) },
      { path: "wallet", element: L(() => import("@/pages/partner/WalletPage")) },
      { path: "support", element: L(() => import("@/pages/support/SupportChatPage")) },
      { path: "org/users", element: L(() => import("@/pages/org/OrgUsersPage")) },
      { path: "settings", handle: { fullBleed: true }, element: L(() => import("@/pages/settings/AccountSettingsPage")) },
      {
        path: "security/2fa",
        element: <Navigate to="/settings?tab=security" replace />,
      },
      {
        path: "admin",
        handle: { fullBleed: true },
        element: (
          <RequireRole role="super_admin">
            <Suspense fallback={<PageLoader />}>
              <AdminLayout />
            </Suspense>
          </RequireRole>
        ),
        children: [
          { index: true, element: L(() => import("@/pages/admin/OverviewPanel")) },
          { path: "system", element: L(() => import("@/pages/admin/SystemStatsPanel")) },
          { path: "companies", element: L(() => import("@/pages/admin/CompaniesPanel")) },
          { path: "mqtt-nodes", element: L(() => import("@/pages/admin/MqttNodesPanel")) },
          { path: "revenue", element: L(() => import("@/pages/admin/RevenuePanel")) },
          { path: "coupons", element: L(() => import("@/pages/admin/CouponsPanel")) },
          { path: "content", element: L(() => import("@/pages/admin/ContentPanel")) },
          { path: "health", element: L(() => import("@/pages/admin/HealthPanel")) },
          { path: "security", element: L(() => import("@/pages/admin/SecurityPanel")) },
          { path: "users", element: L(() => import("@/pages/admin/UsersPanel")) },
          { path: "devices-overview", element: L(() => import("@/pages/admin/DevicesOverviewPanel")) },
          { path: "expiring", element: L(() => import("@/pages/admin/ExpiringPanel")) },
          { path: "controls", element: L(() => import("@/pages/admin/PlatformControlsPanel")) },
          { path: "recovery", element: L(() => import("@/pages/admin/DisasterRecoveryPanel")) },
          { path: "commands", element: L(() => import("@/pages/admin/CommandsReferencePanel")) },
        ],
      },
    ],
  },
  // No root-level `*` fallback: the PublicLayout children already include a
  // splat route that renders NotFoundPage inside the site chrome, so every
  // unmatched path resolves there rather than a bare unstyled div.
]);

export default router;
