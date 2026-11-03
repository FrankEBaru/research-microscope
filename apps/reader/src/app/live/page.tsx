import "@/styles/live.css";
import dynamic from "next/dynamic";
import { liveOn } from "@/live/contract";

const Gallery = dynamic(() => import("./ui").then((mod) => mod.Gallery), { ssr: false });

export default function LivePage() {
  if (!liveOn()) {
    return (
      <main className="live-page">
        <p className="live-off">Live artifacts are off. Set NEXT_PUBLIC_RRM_LIVE_ARTIFACTS=1 to open the mockup gallery.</p>
      </main>
    );
  }
  return <Gallery />;
}
