import { useMemo, useCallback, useRef, useEffect, useState } from "react";
import GridLayout from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import WidgetCard from "./WidgetCard";
import { WIDGET_DRAG_MIME, activeDraggedPaletteItem } from "./DashboardBuilderToolbox";
import { cn } from "@/lib/utils";
import { widgetToGridItem, layoutFromGridItem } from "@/lib/widgets";

export const GRID_COLS = 12;
export const ROW_HEIGHT = 48;
const GRID_MARGIN = [8, 8];
const GRID_PADDING = [8, 8];
const LAYOUT_DEBOUNCE_MS = 450;

function BlynkCellGrid({ width, height }) {
  const [mx, my] = GRID_MARGIN;
  const [px, py] = GRID_PADDING;
  if (width <= 0 || height <= 0) return null;
  const colWidth = (width - px * 2 - mx * (GRID_COLS - 1)) / GRID_COLS;
  const rowStride = ROW_HEIGHT + my;
  const rows = Math.max(1, Math.ceil((height - py) / rowStride));
  const cells = [];
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < GRID_COLS; x += 1) {
      cells.push(
        <span
          key={`${x}-${y}`}
          style={{
            left: px + x * (colWidth + mx),
            top: py + y * rowStride,
            width: colWidth,
            height: ROW_HEIGHT,
          }}
        />
      );
    }
  }
  return <div className="dash-cell-grid">{cells}</div>;
}

export default function DashboardCanvas({
  widgets,
  editing,
  onLayoutChange,
  onCommand,
  onTogglePin,
  onConfigure,
  onDeleteWidget,
  onDuplicateWidget,
  onRotateWidget,
  readOnly,
  className,
  timeRange,
  blynkGrid,
  onDropWidget,
}) {
  const debounceRef = useRef(null);
  const layoutSnapshotRef = useRef("");
  const hostRef = useRef(null);
  const [hostSize, setHostSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = hostRef.current;
    if (!node) return undefined;
    const measure = () => {
      if (node.clientWidth > 0) {
        setHostSize({ width: node.clientWidth, height: node.clientHeight });
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [widgets.length, editing, blynkGrid]);

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    []
  );

  const effectiveWidth = hostSize.width || hostRef.current?.clientWidth || 1200;

  const gridLayout = useMemo(
    () =>
      widgets.map((w) => {
        const item = widgetToGridItem(w, { editing });
        const itemW = Math.min(GRID_COLS, Math.max(1, item.w || 3));
        const itemX = Math.max(0, Math.min(GRID_COLS - itemW, item.x || 0));
        return {
          ...item,
          w: itemW,
          x: itemX,
        };
      }),
    [widgets, editing]
  );

  const persistLayout = useCallback(
    (layout) => {
      if (!onLayoutChange || readOnly) return;
      const key = JSON.stringify(
        layout.map((item) => ({ i: item.i, x: item.x, y: item.y, w: item.w, h: item.h }))
      );
      if (key === layoutSnapshotRef.current) return;
      layoutSnapshotRef.current = key;

      const updates = layout
        .map((item) => {
          const widget = widgets.find((w) => w.id === item.i);
          if (!widget) return null;
          const next = layoutFromGridItem(item);
          const prev = widget.layout || {};
          if (
            prev.x === next.x &&
            prev.y === next.y &&
            prev.w === next.w &&
            prev.h === next.h
          ) {
            return null;
          }
          return { widgetId: item.i, layout: next };
        })
        .filter(Boolean);

      if (updates.length > 0) onLayoutChange(updates);
    },
    [onLayoutChange, readOnly, widgets]
  );

  const handleLayoutChange = useCallback(
    (layout) => {
      if (!editing || readOnly) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => persistLayout(layout), LAYOUT_DEBOUNCE_MS);
    },
    [editing, readOnly, persistLayout]
  );

  const [dragHover, setDragHover] = useState(null);

  const acceptDrop = editing && !readOnly && onDropWidget;
  const dropProps = acceptDrop
    ? {
        onDragOver: (event) => {
          if ([...event.dataTransfer.types].includes(WIDGET_DRAG_MIME)) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
            const container = hostRef.current;
            if (container) {
              const rect = container.getBoundingClientRect();
              const [mx, my] = GRID_MARGIN;
              const [px, py] = GRID_PADDING;
              const colWidth = (rect.width - px * 2 - mx * (GRID_COLS - 1)) / GRID_COLS;
              const rowStride = ROW_HEIGHT + my;
              const relX = event.clientX - rect.left - px;
              const relY = event.clientY - rect.top - py;
              const w = Math.min(GRID_COLS, activeDraggedPaletteItem?.layout?.w || 3);
              const h = activeDraggedPaletteItem?.layout?.h || 2;
              const col = Math.floor(relX / (colWidth + mx));
              const row = Math.floor(relY / rowStride);
              setDragHover({
                x: Math.max(0, Math.min(GRID_COLS - w, col)),
                y: Math.max(0, row),
                w,
                h,
                title: activeDraggedPaletteItem?.title || "Widget",
                colWidth,
                rowStride,
                px,
                py,
                mx,
                my,
              });
            }
          }
        },
        onDragLeave: (event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) {
            setDragHover(null);
          }
        },
        onDrop: (event) => {
          const id = event.dataTransfer.getData(WIDGET_DRAG_MIME);
          setDragHover(null);
          if (!id) return;
          event.preventDefault();

          let dropPos = null;
          const container = hostRef.current;
          if (container) {
            const rect = container.getBoundingClientRect();
            const [mx, my] = GRID_MARGIN;
            const [px, py] = GRID_PADDING;
            const colWidth = (rect.width - px * 2 - mx * (GRID_COLS - 1)) / GRID_COLS;
            const rowStride = ROW_HEIGHT + my;
            const relX = event.clientX - rect.left - px;
            const relY = event.clientY - rect.top - py;
            const w = Math.min(GRID_COLS, activeDraggedPaletteItem?.layout?.w || 3);
            const col = Math.floor(relX / (colWidth + mx));
            const row = Math.floor(relY / rowStride);
            dropPos = {
              x: Math.max(0, Math.min(GRID_COLS - w, col)),
              y: Math.max(0, row),
            };
          }
          onDropWidget(id, dropPos);
        },
      }
    : {};

  const maxWidgetY = useMemo(() => {
    return widgets.reduce((max, w) => {
      const l = w.layout || {};
      return Math.max(max, (l.y || 0) + (l.h || 2));
    }, 0);
  }, [widgets]);

  const minCanvasHeight = Math.max(800, (maxWidgetY + 4) * (ROW_HEIGHT + GRID_MARGIN[1]) + GRID_PADDING[1] * 2);

  if (widgets.length === 0) {
    if (editing && !readOnly) {
      return (
        <div
          ref={hostRef}
          className={cn(
            "dash-blynk-canvas widgets-editable relative flex-1 min-h-[800px] w-full select-none",
            className
          )}
          style={{ minHeight: `${minCanvasHeight}px` }}
          aria-label="Dashboard canvas"
          {...dropProps}
        >
          <BlynkCellGrid width={effectiveWidth} height={Math.max(hostSize.height, minCanvasHeight)} />
          {dragHover ? (
            <div
              className="pointer-events-none absolute z-30 rounded-xl border-2 border-dashed border-primary bg-primary/10 shadow-lg shadow-primary/10 transition-all duration-75 flex flex-col items-center justify-center gap-1 backdrop-blur-xs animate-pulse"
              style={{
                left: dragHover.px + dragHover.x * (dragHover.colWidth + dragHover.mx),
                top: dragHover.py + dragHover.y * dragHover.rowStride,
                width: dragHover.w * dragHover.colWidth + (dragHover.w - 1) * dragHover.mx,
                height: dragHover.h * ROW_HEIGHT + (dragHover.h - 1) * dragHover.my,
              }}
            >
              <span className="rounded-md bg-white/95 px-2.5 py-1 text-xs font-semibold text-primary shadow-xs border border-primary/20 backdrop-blur-md">
                Drop {dragHover.title} ({dragHover.w}×{dragHover.h})
              </span>
              <span className="text-[10px] text-slate-500 font-mono">
                Col {dragHover.x + 1} • Row {dragHover.y + 1}
              </span>
            </div>
          ) : (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center z-10">
              <div className="rounded-2xl border border-dashed border-primary/40 bg-white/90 px-8 py-6 shadow-lg shadow-primary/5 backdrop-blur-md max-w-md">
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </div>
                <p className="text-lg font-bold text-slate-800">Your Canvas is Ready</p>
                <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                  Drag any widget from the toolbox on the left and drop it anywhere on this 12-column grid. Move and resize freely anytime.
                </p>
              </div>
            </div>
          )}
        </div>
      );
    }
    return (
      <div
        className={cn(
          "dash-canvas-empty dashboard-dot-grid flex min-h-[min(520px,60vh)] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-primary/25 bg-card/50",
          className
        )}
      >
        <p className="text-base font-semibold text-foreground">Empty dashboard grid</p>
        <p className="text-sm text-muted-foreground">Switch to Edit to add widgets.</p>
      </div>
    );
  }

  const showCells = Boolean(editing && blynkGrid && !readOnly);

  return (
    <div
      ref={hostRef}
      className={cn(
        "dashboard-rgl relative flex-1 min-h-[800px] w-full",
        showCells ? "dash-blynk-canvas" : "dashboard-dot-grid dash-canvas-grid min-h-[min(720px,calc(100dvh-16rem))] p-2",
        !showCells && editing && "dash-canvas-grid-editing widgets-editable",
        !showCells && !editing && "dash-canvas-grid-view dash-canvas-plain",
        className
      )}
      style={{ minHeight: `${minCanvasHeight}px` }}
      {...dropProps}
    >
      {showCells ? <BlynkCellGrid width={effectiveWidth} height={Math.max(hostSize.height, minCanvasHeight)} /> : null}

      {/* Live Drop Ghost Indicator */}
      {dragHover ? (
        <div
          className="pointer-events-none absolute z-30 rounded-xl border-2 border-dashed border-primary bg-primary/10 shadow-lg shadow-primary/10 transition-all duration-75 flex flex-col items-center justify-center gap-1 backdrop-blur-xs animate-pulse"
          style={{
            left: dragHover.px + dragHover.x * (dragHover.colWidth + dragHover.mx),
            top: dragHover.py + dragHover.y * dragHover.rowStride,
            width: dragHover.w * dragHover.colWidth + (dragHover.w - 1) * dragHover.mx,
            height: dragHover.h * ROW_HEIGHT + (dragHover.h - 1) * dragHover.my,
          }}
        >
          <span className="rounded-md bg-white/95 px-2.5 py-1 text-xs font-semibold text-primary shadow-xs border border-primary/20 backdrop-blur-md">
            Place {dragHover.title} ({dragHover.w}×{dragHover.h})
          </span>
          <span className="text-[10px] text-slate-500 font-mono">
            Col {dragHover.x + 1} • Row {dragHover.y + 1}
          </span>
        </div>
      ) : null}

      {/* Absolute floating banner - does not displace canvas grid */}
      {editing && !readOnly ? (
        <div className="pointer-events-none absolute top-3 right-4 z-20 flex items-center gap-2 select-none">
          <div className="flex items-center gap-2 rounded-full border border-slate-200/90 bg-white/90 px-3 py-1 shadow-xs backdrop-blur-md">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] font-medium text-slate-700">
              Free-form Canvas • 12-col grid
            </span>
          </div>
          <span className="rounded-full border border-slate-200/80 bg-white/90 px-2.5 py-1 font-mono text-[10px] text-slate-600 shadow-xs backdrop-blur-md">
            {widgets.length} {widgets.length === 1 ? "widget" : "widgets"}
          </span>
        </div>
      ) : null}

      <GridLayout
        className="layout relative z-[1]"
        width={effectiveWidth}
        layout={gridLayout}
        cols={GRID_COLS}
        rowHeight={ROW_HEIGHT}
        margin={GRID_MARGIN}
        containerPadding={GRID_PADDING}
        compactType={null}
        preventCollision={false}
        isDraggable={editing && !readOnly}
        isResizable={editing && !readOnly}
        resizeHandles={["s", "w", "e", "n", "sw", "nw", "se", "ne"]}
        draggableHandle=".widget-drag-handle"
        onLayoutChange={handleLayoutChange}
        useCSSTransforms
      >
        {widgets.map((w) => (
          <div key={w.id} className="h-full">
            <WidgetCard
              widget={w}
              editing={editing}
              readOnly={readOnly}
              onCommand={onCommand}
              onTogglePin={onTogglePin}
              onConfigure={onConfigure}
              onDelete={onDeleteWidget}
              onDuplicate={onDuplicateWidget}
              onRotate={onRotateWidget}
              timeRange={timeRange}
            />
          </div>
        ))}
      </GridLayout>
    </div>
  );
}
