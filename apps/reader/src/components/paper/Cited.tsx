"use client";
import { useState } from "react";
import { Prov } from "@/components/ui";

export type CitedRow = { block: string; sent: number; text: string; section?: string };

export function Cited({ rows, rest, onJump }: { rows: CitedRow[]; rest: CitedRow[]; onJump: (row: CitedRow) => void }) {
  const [open, setOpen] = useState(false);
  if (!rows.length) return null;
  const shown = open ? rows.concat(rest) : rows;
  return (
    <div className="cited">
      <Prov kind="paper" text="The paper explains it here" />
      {shown.map((row) => (
        <button type="button" key={row.block} className="cited-row press" onClick={() => onJump(row)}>
          <span className="cited-q">“{row.text}”</span>
          {row.section ? <span className="cited-sec tnum">§{row.section}</span> : null}
        </button>
      ))}
      {rest.length > 0 && (
        <button type="button" className="cited-more press" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {rest.length} more
        </button>
      )}
    </div>
  );
}
