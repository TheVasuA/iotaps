import { MapPin } from "@phosphor-icons/react";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Map widget: plots the device's latest latitude/longitude (Req 7.3, 7.4).
// A full tile map (Leaflet) is heavyweight; for the MVP this shows the live
// coordinates and an embedded OpenStreetMap view when both are present.
export default function MapWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const latMetric = config.latMetric || "lat";
  const lonMetric = config.lonMetric || "lon";

  const latest = useAppSelector(selectLatest(deviceId));
  const lat = readMetric(latest?.data, latMetric);
  const lon = readMetric(latest?.data, lonMetric);

  if (!deviceId) return <UnboundNotice />;

  if (lat == null || lon == null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1 p-3 text-center text-xs text-muted-foreground">
        <MapPin size={22} />
        Waiting for location ({latMetric}/{lonMetric})
      </div>
    );
  }

  const delta = 0.01;
  const bbox = `${lon - delta},${lat - delta},${lon + delta},${lat + delta}`;
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(
    bbox
  )}&layer=mapnik&marker=${lat},${lon}`;

  return (
    <div className="flex h-full flex-col">
      <iframe
        title={`map-${widget.id}`}
        src={src}
        className="h-full w-full flex-1 rounded-md border border-border"
        loading="lazy"
      />
      <div className="px-1 pt-1 text-center text-xs tabular-nums text-muted-foreground">
        {lat.toFixed(5)}, {lon.toFixed(5)}
      </div>
    </div>
  );
}
