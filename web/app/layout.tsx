import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Señales Trading",
  description: "Señales de trading 24/7 — XAUUSD, BTC, ETH",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="site-header">
          <a href="/" className="brand">
            📈 Señales Trading
          </a>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
