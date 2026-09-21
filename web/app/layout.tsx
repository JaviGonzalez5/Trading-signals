import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "Señales Trading",
  description: "Señales de trading 24/7 — XAUUSD, BTC, ETH",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={inter.variable}>
      <body>
        <header className="site-header">
          <div className="header-inner">
            <a href="/" className="brand">
              <span className="brand-mark" />
              Señales Trading
            </a>
            <nav className="header-nav">
              <a href="/" className="nav-link">
                Activos
              </a>
              <a href="/trades" className="nav-link">
                Diario
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
