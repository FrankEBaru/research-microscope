import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "line";
  size?: "md" | "sm";
  children?: ReactNode;
};

export function Button({ variant = "line", size = "md", className, type = "button", ...rest }: Props) {
  const cls = ["btn", `btn--${variant}`, size === "sm" ? "btn--sm" : "", "press", className].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...rest} />;
}

type IconProps = Omit<Props, "children"> & { label: string; children: ReactNode };

export function IconButton({ variant = "line", size = "md", className, label, type = "button", children, ...rest }: IconProps) {
  const cls = ["btn", `btn--${variant}`, "btn--icon", size === "sm" ? "btn--sm" : "", "press", className].filter(Boolean).join(" ");
  return <button type={type} className={cls} aria-label={label} title={label} {...rest}>{children}</button>;
}
