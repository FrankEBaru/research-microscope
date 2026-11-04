/** RRM-102: Research Microscope mark (S18, "the R that underlines"). A soft R whose leg runs on as an underline,
 * with a lens in its eye. Colors come from tokens (.wm-logo in inicio.css). `animate` plays it once: the R appears,
 * the leg underlines left to right (≈0.75 s) and the lens lights up; reduced motion shows it still.
 * Standalone files: public/brand/rm-s18*.svg, s18-anim.svg. */
export default function BrandMark({ size = 22, animate = false }: { size?: number; animate?: boolean }) {
  return (
    <svg className={animate ? "wm-logo is-anim" : "wm-logo"} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path className="wm-r" pathLength={1} d="M10 40.5 V8.5 H20.5 A9.25 9.25 0 0 1 20.5 27 H10" />
      <path className="wm-leg" pathLength={1} d="M20 27.5 C24 33.5 27 40.5 33.5 40.5 H40.5" />
      <circle className="wm-lens" cx="19.6" cy="17.75" r="3.3" />
    </svg>
  );
}
