import "@fontsource-variable/literata/wght.css";
import "@fontsource-variable/literata/wght-italic.css";
import "@fontsource-variable/instrument-sans";
import "katex/dist/katex.min.css";
import "./globals.css";
import "@/styles/atlas.css";

export const metadata = { title: "Reading Microscope", description: "A paper reader that zooms from a question to the source." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
