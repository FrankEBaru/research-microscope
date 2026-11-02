"use client";
import { useEffect, useState } from "react";
import { debugOn } from "@/lib/faults.js";

/** false en el render del servidor y en la hidratación; el valor real llega en el efecto. */
export function useDebug() {
  const [on, setOn] = useState(false);
  useEffect(() => { setOn(debugOn()); }, []);
  return on;
}
