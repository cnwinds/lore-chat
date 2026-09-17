type Props = {
  value: string;
  fallback: string;
  disabled?: boolean;
  onChange: (value: string) => void;
};

/** 厂家显示名：可改；空则按预设回退。 */
export function ProviderLabelField({
  value,
  fallback,
  disabled,
  onChange,
}: Props) {
  return (
    <label className="settings-field">
      <span>厂家名称</span>
      <input
        type="text"
        autoComplete="off"
        value={value || fallback}
        placeholder={fallback}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
