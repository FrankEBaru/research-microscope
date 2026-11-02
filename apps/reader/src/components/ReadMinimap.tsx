"use client";
import { useMemo, useState } from "react";
import { paperKey } from "@/lib/backend.js";
import { layoutOf } from "@/lib/layout.js";

export default function ReadMinimap({ papers, edges, layout, onOpen, explore, openId }: {
  papers: any[];
  edges: any[];
  layout: any;
  onOpen: (id: string) => void;
  explore?: { nodes?: any[]; edges?: any[] } | null;
  openId?: string;
}) {
  const model = useMemo(() => layoutOf({ papers, edges, layout }), [papers, edges, layout]);
  const [big, setBig] = useState(false);
  const points = model.points || [];
  const nodes = explore?.nodes || [];
  const graphEdges = explore?.edges || [];
  const known = useMemo(() => new Set(nodes.map((node) => String(node.id))), [nodes]);
  const at = useMemo(() => {
    const map = new Map<string, any>();
    points.forEach((point: any) => map.set(String(point.corpusid), point));
    return map;
  }, [points]);
  const outside = nodes.filter((node) => !at.has(String(node.id)));
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
        {graphEdges.map((edge: any, index: number) => {
          const a = at.get(String(edge.from));
          const b = at.get(String(edge.to));
          if (!a || !b) return null;
          return <line key={`e${index}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#1d4e89" strokeWidth={3} />;
        })}
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
        {points.map((point: any) => {
          if (!known.has(String(point.corpusid))) return null;
          const sunk = Boolean(byId.get(String(point.corpusid))?.retracted);
          const y = sunk ? Math.min(960, point.y + 40) : point.y;
          const open = String(point.corpusid) === String(openId || "");
          return <circle key={`r${point.corpusid}`} cx={point.x} cy={y} r={open ? 24 : 16} fill="none" stroke="#1d4e89" strokeWidth={open ? 6 : 2} />;
        })}
      </svg>
      {outside.length > 0 && (
        <ul className="explore-rest">
          {outside.map((node) => (
            <li key={node.id}>
              <button type="button" className="link" onClick={() => onOpen(String(node.id))}>{String(node.title || node.id).slice(0, 60)}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
