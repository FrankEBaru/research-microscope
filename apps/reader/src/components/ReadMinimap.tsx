"use client";
import { useMemo, useState } from "react";
import { paperKey } from "@/lib/backend.js";
import { visitWhy } from "@/lib/explore.js";
import { layoutOf } from "@/lib/layout.js";
import type { AtlasCtx } from "./screens/types";

export default function ReadMinimap({ papers, edges, layout, onOpen, explore, openId }: {
  papers: any[];
  edges: any[];
  layout: any;
  onOpen: (id: string) => void;
  explore?: { nodes?: any[]; edges?: any[]; q?: string } | null;
  openId?: string;
  atlasCtx?: AtlasCtx;
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
  const lone = points.length === 0;
  const coords = useMemo(() => {
    if (!lone) return at;
    const map = new Map<string, { x: number; y: number }>();
    const n = Math.max(nodes.length, 1);
    nodes.forEach((node, i) => {
      const ang = -Math.PI / 2 + (i / n) * Math.PI * 2;
      map.set(String(node.id), { x: 800 + Math.cos(ang) * 460, y: 500 + Math.sin(ang) * 300 });
    });
    return map;
  }, [at, lone, nodes]);
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
          const a = coords.get(String(edge.from));
          const b = coords.get(String(edge.to));
          if (!a || !b) return null;
          return <line key={`e${index}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#1d4e89" strokeWidth={3} />;
        })}
        {lone && nodes.map((node) => {
          const spot = coords.get(String(node.id));
          if (!spot) return null;
          const open = String(node.id) === String(openId || "");
          return (
            <g key={`v${node.id}`}>
              <circle cx={spot.x} cy={spot.y} r={open ? 22 : 14} fill="none" stroke="#1d4e89" strokeWidth={open ? 6 : 2} />
              <circle cx={spot.x} cy={spot.y} r={8} fill="#3d5a47" style={{ cursor: "pointer" }} onClick={(event) => { event.stopPropagation(); onOpen(String(node.id)); }} />
            </g>
          );
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
        {!lone && points.map((point: any) => {
          if (!known.has(String(point.corpusid))) return null;
          const sunk = Boolean(byId.get(String(point.corpusid))?.retracted);
          const y = sunk ? Math.min(960, point.y + 40) : point.y;
          const open = String(point.corpusid) === String(openId || "");
          return <circle key={`r${point.corpusid}`} cx={point.x} cy={y} r={open ? 24 : 16} fill="none" stroke="#1d4e89" strokeWidth={open ? 6 : 2} />;
        })}
      </svg>
      {big && nodes.length > 0 && (
        <ul className="explore-rest">
          {nodes.map((node) => {
            const why = visitWhy(node, graphEdges, explore?.q);
            const title = String(node.title || node.id).replace(/\s+/g, " ").trim();
            const cut = title.length > 60;
            return (
              <li key={node.id}>
                <button type="button" className="link" title={cut ? title : undefined} onClick={() => onOpen(String(node.id))}>{cut ? `${title.slice(0, 59)}…` : title}</button>
                {why && <span className="explore-why"> {why}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
