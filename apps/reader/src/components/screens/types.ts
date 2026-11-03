/** Lo que el atlas (mapa grande) y el minimapa del lector necesitan. Se arma en Engine. */
export type AtlasCtx = {
  papers: any[];
  edges: any[];
  layout: any;
  states: Record<string, any>;
  query: string;
  explore: { q?: string; nodes?: any[]; edges?: any[] } | null;
  openId: string;
  laneId?: string;
  onOpen: (id: string, why: string) => void;
  onWant: (id: string) => void;
};
