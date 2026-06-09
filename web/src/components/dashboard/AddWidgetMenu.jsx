import { Dialog, DialogBody } from "@/components/ui/dialog";
import {
  ChartLine,
  ChartBar,
  Gauge,
  Numpad,
  MapPin,
  ToggleLeft,
  Sliders,
  Warning,
} from "@phosphor-icons/react";
import { WIDGET_TYPES, widgetMeta } from "@/lib/widgets";

// Widget picker dialog. Lists the 8 supported widget types (Req 7.3); selecting
// one adds it to the canvas via `onAdd(type)`.
const ICONS = {
  line: ChartLine,
  bar: ChartBar,
  gauge: Gauge,
  value: Numpad,
  map: MapPin,
  toggle: ToggleLeft,
  slider: Sliders,
  alert_badge: Warning,
};

export default function AddWidgetMenu({ open, onClose, onAdd }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a widget"
      description="Pick a widget type to place on the canvas."
    >
      <DialogBody>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {WIDGET_TYPES.map((type) => {
            const meta = widgetMeta(type);
            const Icon = ICONS[type] || Numpad;
            return (
              <button
                key={type}
                type="button"
                onClick={() => {
                  onAdd?.(type);
                  onClose?.();
                }}
                className="flex flex-col items-center gap-2 rounded-lg border border-border bg-background p-3 text-center transition-colors hover:border-primary/60 hover:bg-accent"
                title={meta?.description}
              >
                <Icon size={24} className="text-primary" />
                <span className="text-xs font-medium">{meta?.label}</span>
              </button>
            );
          })}
        </div>
      </DialogBody>
    </Dialog>
  );
}
