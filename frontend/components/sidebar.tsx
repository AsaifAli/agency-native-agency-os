"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
const groups = [
 {label:"WORKSPACE",items:[["Overview","/","◫"],["Organization","/organization","⌘"],["Workforce","/workforce","♙"],["Agent Studio","/agents","✳"],["Tasks","/tasks","☷"],["Operations","/operations","◉"],["Approvals","/approvals","✓"],["Leads","/leads","◎"],["Research & Outreach","/outreach","✉"],["Opportunities","/opportunities","◇"],["Proposals","/proposals","▤"],["Service Catalogue","/service-catalog","▧"],["Contracts","/contracts","▤"],["Onboarding","/onboardings","▧"],["Invoices & Receivables","/invoices","＄"],["Clients","/clients","▣"],["Contacts","/contacts","♧"],["Calls & Transcripts","/calls","☎"]]},
 {label:"INTELLIGENCE",items:[["Workflows","/workflows","⌁"],["Evaluations","/evaluations","◈"],["Skills Library","/capabilities","◇"]]},
 {label:"CONTROL",items:[["Budgets","/budgets","＄"],["Monitoring","/monitoring","◉"],["Security & Audit","/audit","▤"],["Settings","/settings","⚙"]]}
];
export default function Sidebar(){
 const path=usePathname();
 return <aside className="sidebar"><div className="brand"><div className="brand-mark">A</div><div><div className="brand-name">AGENCY OS</div><div className="brand-sub">Founder control plane</div></div></div>
 {groups.map(g=><div key={g.label}><div className="nav-label">{g.label}</div><nav className="nav-list">{g.items.map(([label,href,icon])=><Link key={href} href={href} className={`nav-link ${path===href?"active":""}`}><span className="nav-icon">{icon}</span><span className="nav-text">{label}</span></Link>)}</nav></div>)}
 <div className="sidebar-bottom">Private Agency OS<br/>Founder authority enabled<br/>v0.1 · Foundation build</div></aside>
}
