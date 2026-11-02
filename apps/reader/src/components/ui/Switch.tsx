type Props = { checked: boolean; onChange: (v: boolean) => void; label: string; className?: string };

export function Switch({ checked, onChange, label, className }: Props) {
  return (
    <button type="button" role="switch" aria-checked={checked} className={["tg", checked ? "is-on" : "", className].filter(Boolean).join(" ")} onClick={() => onChange(!checked)}>
      <span className="sw" aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
}
