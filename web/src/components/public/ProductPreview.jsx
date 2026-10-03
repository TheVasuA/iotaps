import { ArrowRight, Sparkle } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import BrandMark from "@/components/BrandMark";
import { MarketingImage } from "@/components/public/MarketingSubpage";
import { landingImageMap } from "@/lib/marketingImages";

/** Hero product stage — wide console screenshot in browser chrome (Blynk-style). */
export default function ProductPreview() {
  return (
    <div className="landing-product-stage relative mx-auto mt-14 max-w-[1100px] sm:mt-16 lg:mt-20">
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-8 -top-12 bottom-8 bg-[radial-gradient(ellipse_70%_50%_at_50%_100%,hsl(var(--primary)/0.35),transparent_70%)]"
      />

      <div className="landing-browser-frame relative overflow-hidden rounded-2xl border border-white/15 bg-zinc-950 shadow-[0_48px_100px_-32px_rgba(0,0,0,0.85)]">
        <div className="flex items-center gap-3 border-b border-white/10 bg-zinc-900/95 px-4 py-3 sm:px-5">
          <div className="flex gap-1.5" aria-hidden>
            <span className="h-2.5 w-2.5 rounded-full bg-zinc-600" />
            <span className="h-2.5 w-2.5 rounded-full bg-zinc-600" />
            <span className="h-2.5 w-2.5 rounded-full bg-zinc-600" />
          </div>
          <div className="mx-auto flex min-w-0 max-w-md flex-1 items-center justify-center gap-2 rounded-md border border-white/10 bg-black/40 px-3 py-1.5">
            <span className="truncate text-[11px] text-white/50">app.iotaps.com/get-started</span>
          </div>
          <Link
            to="/register"
            className="hidden items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[10px] font-bold text-primary-foreground sm:inline-flex"
          >
            <Sparkle size={12} weight="fill" />
            Sign up
          </Link>
        </div>

        <div className="relative">
          <MarketingImage
            src={landingImageMap.heroBrowser}
            alt="IoTAPS analytics and dashboard preview"
            className="aspect-[16/9] max-h-[520px] w-full object-cover object-[center_35%]"
            // Full-bleed inside max-w-[1100px], not a half-column split — the
            // default sizes would under-declare this slot by ~2x at >=lg and
            // the browser would pick the 800px tier for a 1100px render.
            sizes="(min-width: 1100px) 1100px, 100vw"
            priority
          />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/75 via-black/15 to-transparent" />

          <div className="absolute bottom-0 left-0 right-0 flex flex-col gap-4 p-4 sm:flex-row sm:items-end sm:justify-between sm:p-6">
            <div className="flex items-center gap-3">
              <BrandMark size={36} className="rounded-sm shadow-lg ring-2 ring-white/20" />
              <div>
                <p className="text-sm font-bold text-white">iotaps.Console</p>
                <p className="text-xs text-white/55">Dashboards · Devices · Automations</p>
              </div>
            </div>
            <Link
              to="/register"
              className="inline-flex w-fit items-center gap-2 rounded-md bg-white px-4 py-2.5 text-sm font-bold text-black transition hover:bg-white/90"
            >
              Open console
              <ArrowRight size={16} weight="bold" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
