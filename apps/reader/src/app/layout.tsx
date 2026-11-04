import "@fontsource-variable/literata/wght.css";
import "@fontsource-variable/literata/wght-italic.css";
import "@fontsource-variable/instrument-sans";
import "katex/dist/katex.min.css";
import "./globals.css";
import "@/styles/atlas.css";

export const metadata = { title: "Reading Microscope", description: "A paper reader that zooms from a question to the source.", icons: { icon: "/brand/favicon.svg", apple: "/brand/rm-book-app-512.png" } };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <footer className="site-foot">
          Thank you to arXiv for use of its open access interoperability. This product was not reviewed or approved by, nor does it necessarily express or reflect the policies or opinions of, arXiv. · <a href="/licenses">Licenses & use</a>
        </footer>
      </body>
    </html>
  );
}
