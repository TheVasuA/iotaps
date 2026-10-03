// Guards the Maps group in the widget toolbox: each entry must advertise its
// own visual identity. `status_map` previously shipped with `preview: "geomap"`
// and rendered as a byte-identical duplicate of the Geomap tile.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";
import { WIDGET_PALETTE, paletteItem } from "./widgetPalette.js";

const here = dirname(fileURLToPath(import.meta.url));
const previewSource = readFileSync(
  join(here, "../components/dashboard/WidgetPalettePreview.jsx"),
  "utf8"
);
const widgetSource = readFileSync(
  join(here, "../components/dashboard/widgets/MapWidget.jsx"),
  "utf8"
);

// WIDGET_PALETTE is sections -> groups -> items; "Maps" is a group inside the
// "Device metrics" section.
const mapItems =
  WIDGET_PALETTE.flatMap((section) => section.groups ?? []).find(
    (group) => group.label === "Maps"
  )?.items ?? [];

describe("Maps palette group", () => {
  it("exists with the three map entries", () => {
    expect(mapItems.map((item) => item.id)).toEqual(["geomap", "image_map", "status_map"]);
  });

  it("gives every entry a distinct preview kind", () => {
    const previews = mapItems.map((item) => item.preview);
    expect(new Set(previews).size).toBe(previews.length);
  });

  it("renders a preview branch for each advertised kind", () => {
    for (const item of mapItems) {
      expect(previewSource).toContain(`kind === "${item.preview}"`);
    }
  });

  it("keeps all three entries on the map widget type and Pro tier", () => {
    for (const item of mapItems) {
      expect(item.type).toBe("map");
      expect(item.upgrade).toBe("pro");
    }
  });

  it("resolves each id through paletteItem", () => {
    for (const item of mapItems) {
      expect(paletteItem(item.id)?.id).toBe(item.id);
    }
  });
});

describe("MapWidget variant routing", () => {
  it("branches on each palette id so canvas widgets stay distinct", () => {
    expect(widgetSource).toMatch(/paletteId === "image_map"/);
    expect(widgetSource).toMatch(/paletteId === "status_map"/);
  });

  it("falls back to the geographic variant for older widgets", () => {
    // Widgets placed before the three previews diverged carry no paletteId.
    expect(widgetSource).toMatch(/: "geomap"/);
  });
});
