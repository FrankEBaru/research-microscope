"use client";
import { useMemo, useState } from "react";
import { paperKey } from "@/lib/backend.js";
import { layoutOf } from "@/lib/layout.js";

export default function ReadMinimap({ papers, edges, layout, onOpen }: {
  papers: any[];
  edges: any[];
  layout: any;
  onOpen: (id: string) => void;
}) {
  const model = useMemo(() => layoutOf({ papers, edges, layout }), [papers, edges, layout]);
  const [big, setBig] = useState(false);
  const points = model.points || [];
  const byId = useMemo(() => {
    const map = new Map<string, any>();
    (papers || []).forEach((paper) => map.set(paperKey(paper), paper));
    return map;
  }, [papers]);
  return (
    <div
      className={`read-minimap${big ? " is-big" : ""}`}
      onMouseEnter={() => setBig(true)}
      onMouseLeave={() => setBig(false)}
      aria-label="Minimapa de la ráfaga"
    >
      <svg viewBox="0 0 1600 1000">
        {(model.groups || []).filter((group: any) => Number.isFinite(group.cx) && Number.isFinite(group.r)).map((group: any) => (
          <circle key={`g${group.id}`} cx={group.cx} cy={group.cy} r={group.r} fill="#27476b" fillOpacity={0.06} stroke="#27476b" strokeWidth={6} />
        ))}
        {points.map((point: any) => {
          const paper = byId.get(String(point.corpusid));
          const sunk = Boolean(paper?.retracted);
          const focus = Boolean(point.focus) || point.rank < 10;
          return (
            <circle
              key={point.corpusid}
              cx={point.x}
              cy={sunk ? Math.min(960, point.y + 40) : point.y}
              r={focus ? 14 : 7}
              fill={paper?.survey ? "#27476b" : paper?.retracted ? "#8d2a2a" : "#3d5a47"}
              opacity={focus ? 1 : 0.45}
              style={{ cursor: "pointer" }}
              onClick={(event) => { event.stopPropagation(); onOpen(String(point.corpusid)); }}
            />
          );
        })}
      </svg>
    </div>
  );
}
