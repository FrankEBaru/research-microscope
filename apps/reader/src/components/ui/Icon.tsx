const PATHS = {
  search: <><circle cx="8.5" cy="8.5" r="5.5" /><path d="M12.8 12.8 17 17" /></>,
  check: <path d="M4.5 10.5l3.5 3.5 7.5-8" />,
  pen: <><path d="M4 16l1-4 8.5-8.5 3 3L8 15l-4 1z" /><path d="M11.5 5.5l3 3" /></>,
  expand: <path d="M12 4h4v4M8 16H4v-4M16 4l-5 5M4 16l5-5" />,
  close: <path d="M5 5l10 10M15 5L5 15" />,
  copy: <><rect x="7" y="7" width="9" height="9" rx="1.5" /><path d="M13 4H5.5A1.5 1.5 0 0 0 4 5.5V13" /></>,
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={["ic", className].filter(Boolean).join(" ")} width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}
