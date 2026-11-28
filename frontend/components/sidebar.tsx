"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const groups = [
  {
    label: "WORKSPACE",
    items: [
      ["Overview", "/", "◫"],
      ["Organization", "/organization", "⌘"],
      ["Workforce", "/workforce", "♙"],
      ["Agent Studio", "/agents", "✳"],
      ["Tasks", "/tasks", "☷"],
      ["QA & Defects", "/qa", "⚑"],
      ["Operations", "/operations", "◉"],
      ["Private Operations", "/private-ops", "✧"],
      ["Approvals", "/approvals", "✓"],
      ["Leads", "/leads", "◎"],
      ["Outreach", "/outreach", "✉"],
      ["Research Studio", "/research-outreach", "✧"],
      ["Agent Research Review", "/research-drafts", "◈"],
      ["Opportunities", "/opportunities", "◇"],
      ["Proposals", "/proposals", "▤"],
      ["Service Catalogue", "/service-catalog", "▧"],
      ["Contracts", "/contracts", "▤"],
      ["Onboarding", "/onboardings", "▧"],
      ["Invoices & Receivables", "/invoices", "＄"],
      ["Retainers", "/retainers", "◷"],
      ["Client Outcomes", "/outcomes", "◎"],
      ["Clients", "/clients", "▣"],
      ["Contacts", "/contacts", "♧"],
      ["Calls & Transcripts", "/calls", "☎"],
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [
      ["Workflows", "/workflows", "⌁"],
      ["Evaluations", "/evaluations", "◈"],
      ["Skills Library", "/capabilities", "◇"],
    ],
  },
  {
    label: "CONTROL",
    items: [
      ["Budgets", "/budgets", "＄"],
      ["Monitoring", "/monitoring", "◉"],
      ["Security & Audit", "/audit", "▤"],
      ["Settings", "/settings", "⚙"],
    ],
  },
] as const;

export default function Sidebar() {
  const path = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    setIsOpen(false);
  }, [path]);

  useEffect(() => {
    if (!isOpen) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isOpen]);

  return (
    <>
      <button
        type="button"
        className="sidebar-toggle"
        onClick={() => setIsOpen((open) => !open)}
        aria-label={isOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={isOpen}
        aria-controls="agency-sidebar"
      >
        <span aria-hidden="true">{isOpen ? "×" : "☰"}</span>
      </button>

      {isOpen ? (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          tabIndex={-1}
          onClick={() => setIsOpen(false)}
        />
      ) : null}

      <aside
        id="agency-sidebar"
        className="sidebar"
        data-open={isOpen}
        aria-label="Agency OS navigation"
      >
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">A</div>
          <div>
            <div className="brand-name">AGENCY OS</div>
            <div className="brand-sub">Founder control plane</div>
          </div>
        </div>

        {groups.map((group) => (
          <div className="sidebar-group" key={group.label}>
            <div className="nav-label">{group.label}</div>
            <nav className="nav-list" aria-label={group.label.toLowerCase()}>
              {group.items.map(([label, href, icon]) => {
                const active = path === href || (href !== "/" && path.startsWith(`${href}/`));

                return (
                  <Link
                    key={href}
                    href={href}
                    className={active ? "nav-link active" : "nav-link"}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setIsOpen(false)}
                  >
                    <span className="nav-icon" aria-hidden="true">{icon}</span>
                    <span className="nav-text">{label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        ))}

        <div className="sidebar-bottom">
          <strong>Private Agency OS</strong>
          <br />
          Founder authority enabled
          <br />
          v0.1 · Foundation build
        </div>
      </aside>
    </>
  );
}
