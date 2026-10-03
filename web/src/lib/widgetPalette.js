/** Visual widget-box catalog. Each item persists as one of the 8 supported types. */

export const WIDGET_PALETTE = [
  {
    section: "Device metrics",
    groups: [
      {
        label: "Controls",
        items: [
          { id: "switch", type: "toggle", title: "Switch", preview: "switch", layout: { w: 3, h: 2 } },
          { id: "slider", type: "slider", title: "Slider", preview: "slider", layout: { w: 4, h: 2 } },
        ],
      },
      {
        label: "Tiles",
        items: [
          { id: "label", type: "value", title: "Label", preview: "label", layout: { w: 3, h: 2 } },
          { id: "device_count", type: "value", title: "Device count", preview: "count", layout: { w: 3, h: 2 } },
          {
            id: "devices_online",
            type: "value",
            title: "Devices online now",
            preview: "online",
            layout: { w: 3, h: 3 },
          },
        ],
      },
      {
        label: "Tables",
        items: [
          { id: "device_table", type: "value", title: "Device table", preview: "table", layout: { w: 8, h: 6 } },
        ],
      },
      {
        label: "Maps",
        items: [
          { id: "geomap", type: "map", title: "Geomap", preview: "geomap", upgrade: "pro", layout: { w: 6, h: 4 } },
          {
            id: "image_map",
            type: "map",
            title: "Image map",
            preview: "image_map",
            upgrade: "pro",
            layout: { w: 6, h: 4 },
          },
          {
            id: "status_map",
            type: "map",
            title: "Devices connection statuses map",
            // Own preview kind: sharing `geomap` made this card a duplicate of
            // the Geomap tile in the toolbox.
            preview: "status_map",
            upgrade: "pro",
            layout: { w: 6, h: 4 },
          },
        ],
      },
      {
        label: "Charts",
        items: [
          {
            id: "metrics_over_time",
            type: "line",
            title: "Metrics over time, agg.",
            preview: "line_dual",
            layout: { w: 6, h: 4 },
          },
          {
            id: "metric_by_devices",
            type: "line",
            title: "Metric by devices",
            preview: "line_multi",
            layout: { w: 6, h: 4 },
          },
        ],
      },
    ],
  },
  {
    section: "Events",
    groups: [
      {
        label: "Tiles",
        items: [
          { id: "event_count", type: "value", title: "Event count", preview: "event_num", layout: { w: 3, h: 2 } },
        ],
      },
      {
        label: null,
        items: [
          { id: "latest_events", type: "alert_badge", title: "Latest events", preview: "events", layout: { w: 4, h: 4 } },
        ],
      },
      {
        label: "Charts",
        items: [
          { id: "event_bars", type: "bar", title: "Event count", preview: "hbar", layout: { w: 6, h: 4 } },
          {
            id: "events_over_time",
            type: "line",
            title: "All events over time",
            preview: "line_green",
            layout: { w: 6, h: 4 },
          },
          {
            id: "events_breakdown",
            type: "line",
            title: "Events breakdown over time",
            preview: "line_lime",
            layout: { w: 6, h: 4 },
          },
          {
            id: "events_by_org",
            type: "bar",
            title: "Events by organizations",
            preview: "stacked",
            layout: { w: 6, h: 4 },
          },
          {
            id: "events_by_device",
            type: "bar",
            title: "Events by devices",
            preview: "stacked",
            layout: { w: 6, h: 4 },
          },
          {
            id: "events_by_template",
            type: "bar",
            title: "Events by templates",
            preview: "stacked",
            layout: { w: 6, h: 4 },
          },
        ],
      },
    ],
  },
  {
    section: "Platform data",
    badge: "Enterprise",
    groups: [
      {
        label: "Charts",
        items: [
          {
            id: "activations",
            type: "line",
            title: "Activations",
            preview: "line_green",
            upgrade: "enterprise",
            layout: { w: 6, h: 4 },
          },
        ],
      },
    ],
  },
];

const BY_ID = new Map(
  WIDGET_PALETTE.flatMap((section) => section.groups.flatMap((group) => group.items)).map((item) => [
    item.id,
    item,
  ])
);

export function paletteItem(id) {
  return BY_ID.get(id) || null;
}
