import type { ReactNode } from "react";

export function Cap({ children, gap, className }: { children: ReactNode; gap?: boolean; className?: string }) {
  return <div className={["cap", gap ? "cap--gap" : "", className].filter(Boolean).join(" ")}>{children}</div>;
}
