import ChartWidget from "./widgets/ChartWidget";
import GaugeWidget from "./widgets/GaugeWidget";
import ValueWidget from "./widgets/ValueWidget";
import MapWidget from "./widgets/MapWidget";
import ToggleWidget from "./widgets/ToggleWidget";
import SliderWidget from "./widgets/SliderWidget";
import AlertBadgeWidget from "./widgets/AlertBadgeWidget";
import DeviceTableWidget from "./widgets/DeviceTableWidget";

// Maps a widget's `type` to its renderer. Centralizes the 8-type switch so the
// canvas and the public read-only view share the same dispatch (Req 7.3).
const RENDERERS = {
  line: ChartWidget,
  bar: ChartWidget,
  gauge: GaugeWidget,
  value: ValueWidget,
  map: MapWidget,
  toggle: ToggleWidget,
  slider: SliderWidget,
  alert_badge: AlertBadgeWidget,
  table: DeviceTableWidget,
  device_table: DeviceTableWidget,
};

export default function WidgetRenderer({ widget, onCommand, readOnly, timeRange }) {
  if (
    widget.config?.variant === "table" ||
    widget.config?.paletteId === "device_table" ||
    widget.type === "device_table" ||
    widget.type === "table"
  ) {
    return <DeviceTableWidget widget={widget} readOnly={readOnly} />;
  }

  const Component = RENDERERS[widget.type];
  if (!Component) {
    return (
      <div className="flex h-full items-center justify-center p-3 text-center text-xs text-muted-foreground">
        Unknown widget type: {widget.type}
      </div>
    );
  }
  return (
    <Component widget={widget} onCommand={onCommand} readOnly={readOnly} timeRange={timeRange} />
  );
}
