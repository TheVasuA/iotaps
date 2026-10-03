import { SquaresFour } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { WIDGET_PALETTE } from "@/lib/widgetPalette";
import WidgetPalettePreview from "./WidgetPalettePreview";

export let activeDraggedPaletteItem = null;

const MIME = "application/x-iotaps-widget";

/** Light widget box: visual cards, drag onto the canvas or click to add. */
export default function DashboardBuilderToolbox({ onAdd, className }) {
  return (
    <aside className={cn("wb-box", className)} aria-label="Widget box">
      <div className="wb-box-head">
        <SquaresFour size={18} weight="duotone" />
        <p>Widget Box</p>
      </div>
      <div className="wb-box-scroll">
        {WIDGET_PALETTE.map((section) => (
          <section key={section.section} className="wb-section">
            <div className="wb-section-head">
              <h2>{section.section}</h2>
              {section.badge ? <span className="wb-enterprise">{section.badge}</span> : null}
            </div>
            {section.groups.map((group) => (
              <div key={group.label || section.section} className="wb-group">
                {group.label ? <h3>{group.label}</h3> : null}
                <ul>
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="wb-card group hover:border-primary/50 hover:shadow-md transition-all duration-150 active:scale-[0.98]"
                        draggable
                        title="Drag onto the canvas, or click to add"
                        onDragStart={(event) => {
                          activeDraggedPaletteItem = item;
                          event.dataTransfer.setData(MIME, item.id);
                          event.dataTransfer.effectAllowed = "copy";
                        }}
                        onDragEnd={() => {
                          activeDraggedPaletteItem = null;
                        }}
                        onClick={() => onAdd?.(item.id)}
                      >
                        <span className="wb-card-title">{item.title}</span>
                        {item.upgrade ? (
                          <span
                            className={cn(
                              "wb-upgrade",
                              item.upgrade === "enterprise" && "wb-upgrade-enterprise"
                            )}
                          >
                            Upgrade
                          </span>
                        ) : null}
                        <WidgetPalettePreview kind={item.preview} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        ))}
      </div>
    </aside>
  );
}

export const WIDGET_DRAG_MIME = MIME;
