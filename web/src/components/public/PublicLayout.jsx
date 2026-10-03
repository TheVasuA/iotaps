import { useEffect, useRef, useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { List, X, ArrowRight } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import BrandMark from "@/components/BrandMark";
import MarketingFooter from "@/components/public/MarketingFooter";

// Blog and Case Studies stay out of the header: their content is placeholder
// copy, and linking there advertises pages that do not hold up. The routes
// themselves remain registered so old inbound links still resolve.
const mainNav = [
  { to: "/platform", label: "Platform", matchPrefix: "/platform" },
  { to: "/solutions", label: "Solutions", matchPrefix: "/solutions" },
  { to: "/enterprise", label: "Enterprise", matchPrefix: "/enterprise" },
  { to: "/docs", label: "Developers", matchPrefix: "/developers" },
  { to: "/pricing", label: "Pricing", matchPrefix: "/pricing" },
];

const utilityNav = [
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact Us" },
  { to: "/login", label: "Log In" },
];

function headerLinkClass(isActive) {
  return cn(
    "whitespace-nowrap px-2.5 py-2 text-[13px] font-medium text-white/85 transition-colors hover:text-white lg:px-3",
    isActive && "text-white"
  );
}

function mobileLinkClass(isActive) {
  return cn("block py-2.5 text-sm font-medium text-white/90 hover:text-white", isActive && "text-white");
}

// Desktop and mobile must light up the same item for the same pathname, so the
// match lives here rather than in NavLink. NavLink in react-router 6.30 has no
// `isActive` callback prop at all — an older signature was falling into ...rest
// and landing on the DOM as an unknown attribute, and the custom matching was
// therefore never running. "Developers" is the case that shows it: mounted at
// /docs but also reachable at /developers and /developers/*, which NavLink's
// own `to` matching never covers.
export function isNavActive(item, pathname) {
  const bases = item.matchPrefix ? [item.to, item.matchPrefix] : [item.to];
  return bases.some((base) => pathname === base || pathname.startsWith(`${base}/`));
}

export default function PublicLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const toggleRef = useRef(null);
  const mobileNavRef = useRef(null);
  const { pathname } = useLocation();

  // Escape dismisses the disclosure and returns focus to the toggle so
  // keyboard users are not left on the document body.
  useEffect(() => {
    if (!mobileOpen) return undefined;
    function onKeyDown(event) {
      if (event.key === "Escape") {
        setMobileOpen(false);
        toggleRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  // Opening must not leave focus behind on the toggle: park it on the first
  // menu link. Deliberately no focus trap — this is a header disclosure, not a
  // modal, so tabbing out simply continues down the page.
  useEffect(() => {
    if (!mobileOpen) return;
    mobileNavRef.current?.querySelector("a")?.focus();
  }, [mobileOpen]);

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-white focus:px-4 focus:py-2.5 focus:text-sm focus:font-semibold focus:text-slate-900 focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
      >
        Skip to main content
      </a>
      <header className="blynk-site-header sticky top-0 z-50 border-b border-white/[0.08]">
        <div className="c-header-box mx-auto flex h-[70px] max-w-[1440px] items-center gap-4 px-5 sm:px-8">
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <BrandMark size={34} className="rounded-none" />
            <span className="font-brand text-lg font-semibold tracking-tight text-white">iotaps</span>
          </Link>

          <nav className="box-nav hidden min-w-0 flex-1 items-center justify-center lg:flex" aria-label="Primary">
            {mainNav.map((item) => {
              const active = isNavActive(item, pathname);
              return (
                <Link
                  key={item.label}
                  to={item.to}
                  className={headerLinkClass(active)}
                  aria-current={active ? "page" : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="box-nav-actions ml-auto flex shrink-0 items-center gap-0.5 sm:gap-1">
            <nav className="hidden items-center xl:flex" aria-label="Utility">
              {utilityNav.map((item) => {
                const active = isNavActive(item, pathname);
                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    className={headerLinkClass(active)}
                    aria-current={active ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <Link to="/register" className="blynk-header-cta ml-1 hidden sm:inline-flex">
              Sign Up
            </Link>
            <button
              ref={toggleRef}
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center text-white lg:hidden"
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileOpen}
              aria-controls="mobile-nav"
              onClick={() => setMobileOpen((o) => !o)}
            >
              {mobileOpen ? <X size={22} /> : <List size={22} />}
            </button>
          </div>
        </div>

        {/* Always mounted: aria-controls must resolve to a real element even
            while the disclosure is closed. `hidden` removes it from the a11y
            tree and from the tab order without unmounting the node. */}
        <nav
          id="mobile-nav"
          ref={mobileNavRef}
          aria-label="Mobile"
          hidden={!mobileOpen}
          className="border-t border-white/10 px-4 py-4 lg:hidden"
        >
          <ul className="space-y-1">
            {[...mainNav, ...utilityNav].map((item) => {
              const active = isNavActive(item, pathname);
              return (
                <li key={item.label + item.to}>
                  <Link
                    to={item.to}
                    className={mobileLinkClass(active)}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setMobileOpen(false)}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <Link
            to="/register"
            className={cn("blynk-header-cta mt-4 w-full justify-center")}
            onClick={() => setMobileOpen(false)}
          >
            <ArrowRight size={16} weight="bold" aria-hidden />
            Sign Up
          </Link>
        </nav>
      </header>

      {/* tabIndex={-1} so the skip link can land here. `:focus` (not
          `:focus-visible`) because the element is only ever focused
          programmatically — the ring must appear on a mouse click of the skip
          link too, or a keyboard user is left with no evidence the jump worked. */}
      <main
        id="main-content"
        tabIndex={-1}
        className="flex-1 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
      >
        <Outlet />
      </main>

      <MarketingFooter />
    </div>
  );
}
