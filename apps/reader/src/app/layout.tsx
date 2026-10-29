import "@fontsource-variable/inter";
import "@fontsource-variable/source-serif-4";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata = { title: "Microscopio de lectura · prototipo", description: "Un lector de papers con zoom: área, cluster, paper." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
