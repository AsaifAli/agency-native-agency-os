import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/sidebar";
export const metadata: Metadata = { title: "Agency OS | Founder Console", description: "Founder-controlled AI Agency operating system" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><div className="shell"><Sidebar/><main className="main"><header className="topbar"><div className="crumb">AGENCY OS <span className="muted">/ Founder Console</span></div><div className="top-right"><span className="env-pill">DEVELOPMENT</span><div className="avatar">FO</div></div></header>{children}</main></div></body></html>;
}
