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
        {(model.links || []).map((edge: any, index: number) => {
          const a = points.find((point: any) => point.corpusid === edge.citing);
          const b = points.find((point: any) => point.corpusid === edge.cited);
          if (!a || !b) return null;
          return <line key={index} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#6d675d" strokeWidth="8" />;
        })}
        {points.map((point: any) => {
          const paper = byId.get(String(point.corpusid));
          const sunk = Boolean(paper?.retracted);
          return (
            <circle
              key={point.corpusid}
              cx={point.x}
              cy={sunk ? Math.min(960, point.y + 70) : point.y}
              r={point.rank === 0 ? 26 : 16}
              fill={paper?.survey ? "#27476b" : "#8a8175"}
              style={{ cursor: "pointer" }}
              onClick={(event) => { event.stopPropagation(); onOpen(String(point.corpusid)); }}
            />
          );
        })}
      </svg>
    </div>
  );
}
