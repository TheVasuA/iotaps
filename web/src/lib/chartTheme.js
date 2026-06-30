// Shared chart theming helper. Resolves the active role theme + light/dark mode
// (the HSL CSS variables set in styles/index.css) into concrete colours so
// ECharts-based widgets (chart, gauge) render consistently in every theme
// instead of hardcoding light-mode hex values.

function readVar(style, name, fallback) {
  const raw = style.getPropertyValue(name).trim();
  return raw ? `hsl(${raw})` : fallback;
}

function readVarAlpha(style, name, alpha, fallback) {
  const raw = style.getPropertyValue(name).trim();
  return raw ? `hsl(${raw} / ${alpha})` : fallback;
}

/**
 * Resolve the palette used by chart widgets from the document's CSS variables.
 * Call this during render (cheap) and feed the result into the ECharts option
 * so a theme/mode switch repaints with the correct colours.
 */
export function getChartTheme() {
  if (typeof document === "undefined") {
    return {
      primary: "#6d28d9",
      foreground: "#1f2937",
      muted: "#9ca3af",
      border: "#e5e7eb",
      card: "#ffffff",
      grid: "rgba(148,163,184,0.18)",
      areaTop: "rgba(109,40,217,0.25)",
      areaBottom: "rgba(109,40,217,0.02)",
    };
  }
  const style = getComputedStyle(document.documentElement);
  const primary = readVar(style, "--primary", "#6d28d9");
  return {
    primary,
    foreground: readVar(style, "--foreground", "#1f2937"),
    muted: readVar(style, "--muted-foreground", "#9ca3af"),
    border: readVar(style, "--border", "#e5e7eb"),
    card: readVar(style, "--card", "#ffffff"),
    grid: readVarAlpha(style, "--muted-foreground", 0.18, "rgba(148,163,184,0.18)"),
    areaTop: readVarAlpha(style, "--primary", 0.28, "rgba(109,40,217,0.28)"),
    areaBottom: readVarAlpha(style, "--primary", 0.02, "rgba(109,40,217,0.02)"),
  };
}

export default getChartTheme;
