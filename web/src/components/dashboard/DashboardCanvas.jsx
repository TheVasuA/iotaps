import { useMemo, useState, useCallback, useEffect } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import WidgetCard from "./WidgetCard";
import { cn } from "@/lib/utils";

function SortableWidget({ widget, editing, readOnly, onCommand, onTogglePin, onConfigure, onDelete }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: widget.id, disabled: !editing || readOnly });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 50 : "auto",
  };

  const type = widget.type;
  let colSpan = 1;
  let height = "140px";

  switch (type) {
    case "line":
    case "bar":
    case "chart":
      colSpan = 2;
      height = "200px";
      break;
    case "map":
      colSpan = 2;
      height = "220px";
      break;
    case "gauge":
      colSpan = 1;
      height = "210px";
      break;
    case "value":
    case "alert_badge":
      colSpan = 1;
      height = "120px";
      break;
    case "toggle":
    case "slider":
      colSpan = 1;
      height = "130px";
      break;
    default:
      height = "140px";
  }

  return (
    <div
      ref={setNodeRef}
      style={{ ...style, gridColumn: `span ${colSpan}`, height }}
      {...attributes}
      className={cn("relative", isDragging && "ring-2 ring-primary rounded-xl")}
    >
      <WidgetCard
        widget={widget}
        editing={editing}
        readOnly={readOnly}
        onCommand={onCommand}
        onTogglePin={onTogglePin}
        onConfigure={onConfigure}
        onDelete={onDelete}
        dragListeners={listeners}
      />
    </div>
  );
}

export default function DashboardCanvas({
  widgets,
  editing,
  onReorder,
  onCommand,
  onTogglePin,
  onConfigure,
  onDeleteWidget,
  readOnly,
}) {
  const [localOrder, setLocalOrder] = useState(null);
  const [activeId, setActiveId] = useState(null);

  // Clear local order when widgets change (new widget added/removed)
  useEffect(() => {
    setLocalOrder(null);
  }, [widgets.length]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  // Use local order if mid-drag, else sort from props
  const ordered = useMemo(() => {
    if (localOrder) return localOrder;
    return [...widgets].sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      const ay = a.layout?.y ?? 999;
      const by = b.layout?.y ?? 999;
      if (ay !== by) return ay - by;
      return (a.layout?.x ?? 0) - (b.layout?.x ?? 0);
    });
  }, [widgets, localOrder]);

  const widgetIds = useMemo(() => ordered.map((w) => w.id), [ordered]);
  const activeWidget = activeId ? ordered.find((w) => w.id === activeId) : null;

  const handleDragStart = useCallback((event) => {
    setActiveId(event.active.id);
  }, []);

  const handleDragEnd = useCallback((event) => {
    setActiveId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) {
      setLocalOrder(null);
      return;
    }

    const oldIndex = ordered.findIndex((w) => w.id === active.id);
    const newIndex = ordered.findIndex((w) => w.id === over.id);
    if (oldIndex === -1 || newIndex === -1) {
      setLocalOrder(null);
      return;
    }

    const newOrder = arrayMove(ordered, oldIndex, newIndex);
    setLocalOrder(newOrder);

    // Persist: assign grid positions based on new order
    if (onReorder) {
      const layoutUpdates = newOrder.map((w, i) => ({
        widgetId: w.id,
        layout: {
          x: (i % 4) * 3,
          y: Math.floor(i / 4) * 3,
          w: w.layout?.w || 3,
          h: w.layout?.h || 2,
        },
      }));
      onReorder(layoutUpdates);
    }
  }, [ordered, onReorder]);

  if (widgets.length === 0) {
    return (
      <div className="dashboard-dot-grid flex min-h-[40vh] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border">
        <div className="text-4xl">📊</div>
        <p className="text-base font-medium text-foreground">Your dashboard is empty</p>
        {!readOnly && (
          <p className="text-sm text-muted-foreground">
            Click &ldquo;Add widget&rdquo; to start building
          </p>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "dashboard-dot-grid min-h-[40vh] rounded-2xl border p-2 transition-all",
        editing ? "border-primary/30" : "border-transparent"
      )}
    >
      {editing && (
        <p className="mb-2 text-center text-xs text-muted-foreground">
          ✏️ Drag widgets to reorder
        </p>
      )}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={widgetIds} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
            {ordered.map((w) => (
              <SortableWidget
                key={w.id}
                widget={w}
                editing={editing}
                readOnly={readOnly}
                onCommand={onCommand}
                onTogglePin={onTogglePin}
                onConfigure={onConfigure}
                onDelete={onDeleteWidget}
              />
            ))}
          </div>
        </SortableContext>

        <DragOverlay>
          {activeWidget ? (
            <div className="rounded-xl shadow-2xl ring-2 ring-primary/60 opacity-90" style={{ height: "140px", width: "200px" }}>
              <WidgetCard
                widget={activeWidget}
                editing={false}
                readOnly={true}
                onCommand={() => {}}
              />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

export const ROW_HEIGHT = 70;
