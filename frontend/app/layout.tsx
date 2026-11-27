import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import Sidebar from "@/components/sidebar";
import SessionRefresh from "@/components/session-refresh";
import ThemeControl from "@/components/theme-control";

export const metadata: Metadata = {
  title: "Agency OS | Founder Console",
  description: "Founder-controlled AI Agency operating system",
};

const themeBootstrap = `try { const saved = localStorage.getItem("agency-os-theme"); if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved); else document.documentElement.removeAttribute("data-theme"); } catch { document.documentElement.removeAttribute("data-theme"); }`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <Script id="agency-os-theme-bootstrap" strategy="beforeInteractive">
          {themeBootstrap}
        </Script>
      </head>
      <body>
        <SessionRefresh />
        <div className="shell">
          <Sidebar />
          <main className="main">
            <header className="topbar">
              <div className="crumb">AGENCY OS <span className="muted">/ Founder Console</span></div>
              <div className="top-right">
                <ThemeControl />
                <span className="env-pill">DEVELOPMENT</span>
                <div className="avatar">FO</div>
              </div>
            </header>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
