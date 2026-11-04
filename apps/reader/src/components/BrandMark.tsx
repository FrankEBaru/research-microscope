/** RRM-102: Reading Microscope mark. A text line enters the lens and becomes a wave ("can you hear it").
 * Colors come from tokens (.wm-logo in inicio.css). `animate` draws it once (≤1.25 s); reduced motion shows it still.
 * Standalone files: public/brand/rm-wave*.svg. */
export default function BrandMark({ size = 22, animate = false }: { size?: number; animate?: boolean }) {
  return (
    <svg className={animate ? "wm-logo is-anim" : "wm-logo"} width={size} height={size} viewBox="0 0 32 32" fill="none" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <circle className="wm-ring" cx="16" cy="16" r="10.5" pathLength={1} strokeWidth="3" transform="rotate(-90 16 16)" />
      <path className="wm-line" d="M1.5 16 H8.5 C10.5 16 10.5 10.5 13 10.5 C15.5 10.5 16.5 21.5 19 21.5 C21.5 21.5 21.5 16 23.5 16 H30.5" pathLength={1} strokeWidth="2.6" />
    </svg>
  );
}
