import { Check, X } from "@phosphor-icons/react";

/** Editor bar — console title field plus primary save. */
export default function DashboardBuilderHeader({
  name,
  onNameChange,
  onSave,
  onCancel,
  saving,
}) {
  return (
    <header className="dash-builder-header">
      <label className="dash-builder-name">
        <span>Name</span>
        <input
          value={name}
          onChange={(e) => onNameChange?.(e.target.value)}
          className="dash-builder-name-input"
          placeholder="Dashboard name"
          aria-label="Dashboard name"
        />
      </label>
      <div className="dash-builder-header-actions">
        <button type="button" className="dash-builder-cancel" onClick={onCancel}>
          <X size={16} weight="bold" />
          Cancel
        </button>
        <button type="button" className="dash-builder-apply" onClick={onSave} disabled={saving}>
          <Check size={16} weight="bold" />
          {saving ? "Saving…" : "Apply changes"}
        </button>
      </div>
    </header>
  );
}
