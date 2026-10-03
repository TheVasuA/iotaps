import { useEffect } from "react";
import { Link } from "react-router-dom";
import BrandMark from "@/components/BrandMark";
import ThemeModeToggle from "@/components/ThemeModeToggle";
import AuthCard from "@/components/auth/AuthCard";
import { cn } from "@/lib/utils";

// Blynk-inspired centered auth frame (login, register, password reset).
export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
  topRight,
  className,
  /** @deprecated use subtitle */
  description,
}) {
  const helper = subtitle ?? description;

  // Public auth must use Blynk lime tokens (not a leftover admin/purple session theme).
  useEffect(() => {
    const root = document.documentElement;
    const prev = root.getAttribute("data-theme");
    root.setAttribute("data-theme", "project-center");
    return () => {
      if (prev) root.setAttribute("data-theme", prev);
    };
  }, []);

  return (
    <div className={cn("auth-page relative flex min-h-screen flex-col items-center justify-center px-4 py-12", className)}>
      <div className="absolute right-4 top-4 flex items-center gap-2">
        {topRight ?? <ThemeModeToggle />}
      </div>
      <div className="absolute bottom-4 right-6 hidden gap-4 text-xs sm:flex">
        <Link to="/privacy" className="text-[#2563eb] hover:underline">
          Privacy Policy
        </Link>
        <Link to="/terms" className="text-[#2563eb] hover:underline">
          Terms of Service
        </Link>
      </div>

      <Link to="/" className="mb-6 block transition-opacity hover:opacity-90" aria-label="IoTAPS home">
        <BrandMark size={48} className="rounded-none shadow-sm" />
      </Link>

      <AuthCard title={title} subtitle={helper} footer={footer}>
        {children}
      </AuthCard>
    </div>
  );
}
