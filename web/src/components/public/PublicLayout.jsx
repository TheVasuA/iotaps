import { Outlet, NavLink, Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import ThemeModeToggle from "@/components/ThemeModeToggle";
import { buttonVariants } from "@/components/ui/button";

// Public (unauthenticated) website shell (Task 21.1, Req 31.1). Frames the
// informational pages with a marketing header/nav and a footer linking to the
// legal and support pages. Visitors can reach these without a session, so the
// header offers sign-in / get-started actions rather than the app nav.

const primaryNav = [
  { to: "/pricing", label: "Pricing" },
  { to: "/docs", label: "Docs" },
  { to: "/about", label: "About" },
  { to: "/faq", label: "FAQ" },
  { to: "/status", label: "Status" },
  { to: "/changelog", label: "Changelog" },
];

const footerSections = [
  {
    title: "Product",
    links: [
      { to: "/pricing", label: "Pricing" },
      { to: "/docs", label: "Docs / API" },
      { to: "/changelog", label: "Changelog" },
      { to: "/status", label: "Status" },
    ],
  },
  {
    title: "Company",
    links: [
      { to: "/about", label: "About" },
      { to: "/contact", label: "Contact" },
      { to: "/faq", label: "FAQ" },
    ],
  },
  {
    title: "Legal",
    links: [
      { to: "/terms", label: "Terms" },
      { to: "/privacy", label: "Privacy" },
      { to: "/refund-policy", label: "Refund Policy" },
    ],
  },
];

function navLinkClass({ isActive }) {
  return cn(
    "rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-accent",
    isActive && "bg-accent text-accent-foreground"
  );
}

export default function PublicLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-lg font-semibold text-primary">
              IoTAPS
            </Link>
            <nav className="hidden gap-1 md:flex">
              {primaryNav.map((item) => (
                <NavLink key={item.to} to={item.to} className={navLinkClass}>
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <ThemeModeToggle />
            <Link to="/login" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              Sign in
            </Link>
            <Link to="/register" className={buttonVariants({ size: "sm" })}>
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto grid max-w-6xl gap-8 px-6 py-10 sm:grid-cols-2 md:grid-cols-4">
          <div className="space-y-2">
            <span className="text-lg font-semibold text-primary">IoTAPS</span>
            <p className="text-xs text-muted-foreground">IoT Automation Platform Services</p>
            <p className="text-sm text-muted-foreground">
              Multi-tenant IoT platform for device fleets, dashboards, and
              automation.
            </p>
          </div>
          {footerSections.map((section) => (
            <div key={section.title} className="space-y-2">
              <h2 className="text-sm font-semibold text-foreground">
                {section.title}
              </h2>
              <ul className="space-y-1.5">
                {section.links.map((link) => (
                  <li key={link.to}>
                    <Link
                      to={link.to}
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="border-t border-border">
          <p className="mx-auto max-w-6xl px-6 py-4 text-xs text-muted-foreground">
            © {new Date().getFullYear()} IoTAPS — IoT Automation Platform Services. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
