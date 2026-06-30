import { lazy, Suspense } from "react";
import { createBrowserRouter } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
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

// Public pages — lazy loaded
const PublicLayout = lazy(() => import("@/components/public/PublicLayout"));
const LandingPage = lazy(() => import("@/pages/public/LandingPage"));
const PricingPage = lazy(() => import("@/pages/public/PricingPage"));
const AboutPage = lazy(() => import("@/pages/public/AboutPage"));
const ContactPage = lazy(() => import("@/pages/public/ContactPage"));
const DocsPage = lazy(() => import("@/pages/public/DocsPage"));
const TermsPage = lazy(() => import("@/pages/public/TermsPage"));
const PrivacyPage = lazy(() => import("@/pages/public/PrivacyPage"));
const RefundPolicyPage = lazy(() => import("@/pages/public/RefundPolicyPage"));
const StatusPage = lazy(() => import("@/pages/public/StatusPage"));
const FaqPage = lazy(() => import("@/pages/public/FaqPage"));
const ChangelogPage = lazy(() => import("@/pages/public/ChangelogPage"));

// Auth pages
const LoginPage = lazy(() => import("@/pages/auth/LoginPage"));
const RegisterPage = lazy(() => import("@/pages/auth/RegisterPage"));
const ForgotPasswordPage = lazy(() => import("@/pages/auth/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("@/pages/auth/ResetPasswordPage"));
const TwoFactorSetupPage = lazy(() => import("@/pages/auth/TwoFactorSetupPage"));

// App pages — lazy loaded (heaviest)
const DashboardPage = lazy(() => import("@/pages/dashboards/DashboardPage"));
const DeviceListPage = lazy(() => import("@/pages/devices/DeviceListPage"));
const DeviceDetailPage = lazy(() => import("@/pages/devices/DeviceDetailPage"));
const WebFlasherPage = lazy(() => import("@/pages/devices/WebFlasherPage"));
const MqttExplorerPage = lazy(() => import("@/pages/devices/MqttExplorerPage"));
const RuleListPage = lazy(() => import("@/pages/rules/RuleListPage"));
const RuleEditorPage = lazy(() => import("@/pages/rules/RuleEditorPage"));
const BillingPage = lazy(() => import("@/pages/billing/BillingPage"));
const ReferralPage = lazy(() => import("@/pages/referrals/ReferralPage"));
const WalletPage = lazy(() => import("@/pages/partner/WalletPage"));
const SupportChatPage = lazy(() => import("@/pages/support/SupportChatPage"));

// Admin pages
const AdminLayout = lazy(() => import("@/pages/admin/AdminLayout"));
const OverviewPanel = lazy(() => import("@/pages/admin/OverviewPanel"));
const CompaniesPanel = lazy(() => import("@/pages/admin/CompaniesPanel"));
const MqttNodesPanel = lazy(() => import("@/pages/admin/MqttNodesPanel"));
const RevenuePanel = lazy(() => import("@/pages/admin/RevenuePanel"));
const CouponsPanel = lazy(() => import("@/pages/admin/CouponsPanel"));
const ContentPanel = lazy(() => import("@/pages/admin/ContentPanel"));
const HealthPanel = lazy(() => import("@/pages/admin/HealthPanel"));
const SecurityPanel = lazy(() => import("@/pages/admin/SecurityPanel"));

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
    ],
  },
  { path: "/login", element: L(() => import("@/pages/auth/LoginPage")) },
  { path: "/register", element: L(() => import("@/pages/auth/RegisterPage")) },
  { path: "/forgot-password", element: L(() => import("@/pages/auth/ForgotPasswordPage")) },
  { path: "/reset-password", element: L(() => import("@/pages/auth/ResetPasswordPage")) },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: "dashboard", element: L(() => import("@/pages/dashboards/DashboardPage")) },
      { path: "devices", element: L(() => import("@/pages/devices/DeviceListPage")) },
      { path: "devices/:id", element: L(() => import("@/pages/devices/DeviceDetailPage")) },
      { path: "flasher", element: L(() => import("@/pages/devices/WebFlasherPage")) },
      { path: "explorer", element: L(() => import("@/pages/devices/MqttExplorerPage")) },
      { path: "rules", element: L(() => import("@/pages/rules/RuleListPage")) },
      { path: "rules/:id", element: L(() => import("@/pages/rules/RuleEditorPage")) },
      { path: "billing", element: L(() => import("@/pages/billing/BillingPage")) },
      { path: "referrals", element: L(() => import("@/pages/referrals/ReferralPage")) },
      { path: "wallet", element: L(() => import("@/pages/partner/WalletPage")) },
      { path: "support", element: L(() => import("@/pages/support/SupportChatPage")) },
      { path: "security/2fa", element: L(() => import("@/pages/auth/TwoFactorSetupPage")) },
      {
        path: "admin",
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
  {
    path: "*",
    element: (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Page not found
      </div>
    ),
  },
]);

export default router;
