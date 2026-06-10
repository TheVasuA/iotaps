import { createBrowserRouter } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
import RequireAuth from "@/components/RequireAuth";
import PublicLayout from "@/components/public/PublicLayout";
import Placeholder from "@/pages/Placeholder";
import LandingPage from "@/pages/public/LandingPage";
import PricingPage from "@/pages/public/PricingPage";
import AboutPage from "@/pages/public/AboutPage";
import ContactPage from "@/pages/public/ContactPage";
import DocsPage from "@/pages/public/DocsPage";
import TermsPage from "@/pages/public/TermsPage";
import PrivacyPage from "@/pages/public/PrivacyPage";
import RefundPolicyPage from "@/pages/public/RefundPolicyPage";
import StatusPage from "@/pages/public/StatusPage";
import FaqPage from "@/pages/public/FaqPage";
import ChangelogPage from "@/pages/public/ChangelogPage";
import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import ForgotPasswordPage from "@/pages/auth/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/auth/ResetPasswordPage";
import TwoFactorSetupPage from "@/pages/auth/TwoFactorSetupPage";
import DeviceListPage from "@/pages/devices/DeviceListPage";
import DeviceDetailPage from "@/pages/devices/DeviceDetailPage";
import WebFlasherPage from "@/pages/devices/WebFlasherPage";
import MqttExplorerPage from "@/pages/devices/MqttExplorerPage";
import DashboardPage from "@/pages/dashboards/DashboardPage";
import RuleListPage from "@/pages/rules/RuleListPage";
import RuleEditorPage from "@/pages/rules/RuleEditorPage";
import BillingPage from "@/pages/billing/BillingPage";
import ReferralPage from "@/pages/referrals/ReferralPage";
import WalletPage from "@/pages/partner/WalletPage";
import SupportChatPage from "@/pages/support/SupportChatPage";
import AdminLayout from "@/pages/admin/AdminLayout";
import OverviewPanel from "@/pages/admin/OverviewPanel";
import CompaniesPanel from "@/pages/admin/CompaniesPanel";
import MqttNodesPanel from "@/pages/admin/MqttNodesPanel";
import RevenuePanel from "@/pages/admin/RevenuePanel";
import CouponsPanel from "@/pages/admin/CouponsPanel";
import ContentPanel from "@/pages/admin/ContentPanel";
import HealthPanel from "@/pages/admin/HealthPanel";
import SecurityPanel from "@/pages/admin/SecurityPanel";
import RequireRole from "@/components/RequireRole";

// Routing.
//   - Public informational website (Req 31): "/" + /pricing, /about, /contact,
//     /docs, /terms, /privacy, /refund-policy, /status, /faq, /changelog under
//     PublicLayout (no auth, task 21.1).
//   - Auth screens (task 2.8) are public.
//   - The authenticated app shell is a pathless layout guarded by RequireAuth;
//     its routes (/dashboard, /devices, ...) are unchanged.
//   - /public/d/:token -> task 8.3 (public read-only dashboard).
export const router = createBrowserRouter([
  {
    path: "/",
    element: <PublicLayout />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "pricing", element: <PricingPage /> },
      { path: "about", element: <AboutPage /> },
      { path: "contact", element: <ContactPage /> },
      { path: "docs", element: <DocsPage /> },
      { path: "terms", element: <TermsPage /> },
      { path: "privacy", element: <PrivacyPage /> },
      { path: "refund-policy", element: <RefundPolicyPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "faq", element: <FaqPage /> },
      { path: "changelog", element: <ChangelogPage /> },
    ],
  },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  {
    path: "/public/d/:token",
    element: (
      <Placeholder
        title="Public dashboard"
        note="Read-only public dashboards are built in task 8.3."
      />
    ),
  },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      {
        path: "dashboard",
        element: <DashboardPage />,
      },
      {
        path: "devices",
        element: <DeviceListPage />,
      },
      {
        path: "devices/:id",
        element: <DeviceDetailPage />,
      },
      {
        path: "flasher",
        element: <WebFlasherPage />,
      },
      {
        path: "explorer",
        element: <MqttExplorerPage />,
      },
      {
        path: "rules",
        element: <RuleListPage />,
      },
      {
        path: "rules/:id",
        element: <RuleEditorPage />,
      },
      {
        path: "billing",
        element: <BillingPage />,
      },
      {
        path: "referrals",
        element: <ReferralPage />,
      },
      {
        path: "wallet",
        element: <WalletPage />,
      },
      {
        path: "support",
        element: <SupportChatPage />,
      },
      { path: "security/2fa", element: <TwoFactorSetupPage /> },
      {
        path: "admin",
        element: (
          <RequireRole role="super_admin">
            <AdminLayout />
          </RequireRole>
        ),
        children: [
          { index: true, element: <OverviewPanel /> },
          { path: "companies", element: <CompaniesPanel /> },
          { path: "mqtt-nodes", element: <MqttNodesPanel /> },
          { path: "revenue", element: <RevenuePanel /> },
          { path: "coupons", element: <CouponsPanel /> },
          { path: "content", element: <ContentPanel /> },
          { path: "health", element: <HealthPanel /> },
          { path: "security", element: <SecurityPanel /> },
        ],
      },
    ],
  },
  {
    path: "*",
    element: <Placeholder title="Not found" note="The requested page does not exist." />,
  },
]);

export default router;
