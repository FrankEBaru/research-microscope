/** RRM-102: Reading Microscope mark. An open book whose spine is a biconvex lens.
 * Colors come from tokens (.wm-logo in inicio.css). `animate` opens it once (≈1.05 s); reduced motion shows it still.
 * Standalone files: public/brand/rm-book*.svg. */
export default function BrandMark({ size = 22, animate = false }: { size?: number; animate?: boolean }) {
  return (
    <svg className={animate ? "wm-logo is-anim" : "wm-logo"} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path className="wm-pl" d="M20.02 10.60 C15 8.6 9 8.3 2.5 10 V38.5 C9 36.8 15 37.4 21.35 40.60 C17.38 32.68 16.94 19.66 20.02 10.60 Z" />
      <path className="wm-pr" d="M27.98 10.60 C33 8.6 39 8.3 45.5 10 V38.5 C39 36.8 33 37.4 26.65 40.60 C30.62 32.68 31.06 19.66 27.98 10.60 Z" />
      <path className="wm-lens" d="M24 7 C30 14.5 30 33.5 24 41 C18 33.5 18 14.5 24 7 Z" />
    </svg>
  );
}
