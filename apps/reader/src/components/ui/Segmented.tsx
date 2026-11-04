import type { ReactNode } from "react";

export type Option<T extends string> = { value: T; label: ReactNode };

type Props<T extends string> = {
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
  label?: string;
  className?: string;
};

function Group<T extends string>({ cls, options, value, onChange, label, className }: Props<T> & { cls: string }) {
  return (
    <div role="tablist" aria-label={label} className={[cls, className].filter(Boolean).join(" ")}>
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" className="press" aria-selected={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>(p: Props<T>) { return <Group cls="seg" {...p} />; }
export function Tabs<T extends string>(p: Props<T>) { return <Group cls="tabs" {...p} />; }
