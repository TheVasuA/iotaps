import { marketingImageManifest } from "./marketingImages.generated.js";

/**
 * Static marketing photography (served from /public/marketing).
 *
 * Entries are enriched by scripts/optimize-images.mjs with intrinsic
 * dimensions and AVIF/WebP/JPEG renditions at two widths (see
 * marketingImages.generated.js). Falls back to the plain JPEG path when an
 * entry is missing so the original .jpg files alone still render every page.
 */
function image(stem, fallbackPath) {
  return marketingImageManifest[stem] ?? fallbackPath;
}

/**
 * Default `sizes` for MarketingImage. Below `lg` the marketing grid stacks
 * photo slots full-bleed (so 100vw); from `lg` up, the max-w-7xl splits put a
 * photo in roughly half the container (510-720px), which `min(50vw, 640px)`
 * tracks across viewports. A caller with an unusual slot can pass its own.
 */
export const marketingImageSizes = "(min-width: 1024px) min(50vw, 640px), 100vw";

/**
 * Build a `NNNw` srcset string from manifest variant entries (ascending).
 * Also accepts a bare URL string — the legacy single-candidate shape — so a
 * stale generated manifest still renders instead of dropping the <source>.
 */
export function buildSrcSet(entries) {
  if (!entries) return undefined;
  if (typeof entries === "string") return entries || undefined;
  if (!Array.isArray(entries)) return undefined;
  const candidates = entries
    .map((entry) => {
      if (typeof entry === "string") return entry;
      if (!entry?.url || !entry.width) return null;
      return `${entry.url} ${entry.width}w`;
    })
    .filter(Boolean);
  return candidates.length > 0 ? candidates.join(", ") : undefined;
}

export const marketingImages = {
  /** Operations / control-room style fleet monitoring */
  heroFleet: image("hero-fleet", "/marketing/hero-fleet.jpg"),
  /** Developer at desk with laptop — console & product hero */
  consoleDesk: image("console-desk", "/marketing/console-desk.jpg"),
  /** Greenhouse / precision agriculture */
  solutionsAgriculture: image("solutions-agriculture", "/marketing/solutions-agriculture.jpg"),
  /** Manufacturing & industrial automation */
  industrialPlant: image("industrial-plant", "/marketing/industrial-plant.jpg"),
  /** Analytics screens — dashboards & data viz */
  analyticsDashboard: image("analytics-dashboard", "/marketing/analytics-dashboard.jpg"),
  /** Wide hero — laptop analytics / console preview */
  heroConsolePreview: image("hero-console-preview", "/marketing/hero-console-preview.jpg"),
  /** Solar / energy & utilities */
  energyGrid: image("energy-grid", "/marketing/energy-grid.jpg"),
  /** Warehouse & logistics fleets */
  fleetLogistics: image("fleet-logistics", "/marketing/fleet-logistics.jpg"),
};

/** Landing section → image (one source of truth, no mismatched repeats). */
export const landingImageMap = {
  heroBrowser: marketingImages.heroConsolePreview,
  solutionsHero: marketingImages.industrialPlant,
  solutionsAccent: marketingImages.solutionsAgriculture,
  featuredRuleEngine: marketingImages.analyticsDashboard,
  testimonial: marketingImages.energyGrid,
  showcaseGetStarted: marketingImages.consoleDesk,
  showcaseFleet: marketingImages.fleetLogistics,
  showcaseDashboards: marketingImages.analyticsDashboard,
};
