"use client";
import type { ReactNode } from "react";
import "@/styles/faults.css";
import { friendly } from "@/lib/faults.js";
import { useDebug } from "./useDebug";

/** Ausencia (siempre visible) o falla (aviso corto; el detalle va al panel de diagnóstico). */
export default function Notice({ kind, code, children, onRetry }: {
  kind: "absence" | "fault";
  code?: string;
  children?: ReactNode;
  onRetry?: () => void;
}) {
  const debug = useDebug();
  const text = kind === "fault" ? (children ?? friendly(code || "F-RENDER")) : children;
  return (
    <p className={`notice notice-${kind}`} role={kind === "fault" ? "alert" : "status"} data-fault={kind === "fault" ? code || "" : undefined}>
      {text}
      {kind === "fault" && onRetry && <button type="button" className="notice-retry press" onClick={onRetry}>Reintentar</button>}
      {debug && code && <span className="notice-code"> · {code}</span>}
    </p>
  );
}
