"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Opportunity = { id: string; title: string; currency: string; stage: string; amount_minor: number };
type ServiceOffering = { id: string; code: string; version: number; name: string; service_line: string; description: string; indicative_price_minor: number | null; currency: string; deliverables: string[]; exclusions: string[]; status: string };
type Proposal = {
  id: string;
  service_offering_id: string | null;
  service_offering_snapshot: Record<string, unknown> | null;
  workspace_id: string;
  opportunity_id: string;
  title: string;
  service_line: string;
  scope_summary: string;
  deliverables: string[];
  assumptions: string[];
  exclusions: string[];
  amount_minor: number;
  currency: string;
  validity_days: number;
  status: string;
  approval_id: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
};

function money(amountMinor: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amountMinor / 100);
}
function lines(value: string) { return value.split("\n").map(item => item.trim()).filter(Boolean); }

export default function ProposalsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [offerings, setOfferings] = useState<ServiceOffering[]>([]);
  const [serviceOfferingId, setServiceOfferingId] = useState("");
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [opportunityId, setOpportunityId] = useState("");
  const [title, setTitle] = useState("");
  const [serviceLine, setServiceLine] = useState("");
  const [scope, setScope] = useState("");
  const [deliverables, setDeliverables] = useState("");
  const [assumptions, setAssumptions] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [amount, setAmount] = useState("");
  const [validity, setValidity] = useState("30");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState("");

  useEffect(() => {
    async function loadWorkspaces() {
      try {
        if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
        setWorkspaces(rows);
        if (rows[0]) setWorkspace(rows[0].id);
        else setLoading(false);
      } catch (e) {
        setError((e as Error).message);
        setLoading(false);
      }
    }
    void loadWorkspaces();
  }, []);

  const loadData = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true);
    setError("");
    try {
      const [opps, drafts, catalogue] = await Promise.all([
        api<Opportunity[]>(`/v1/orgs/${orgId()}/opportunities?workspace_id=${encodeURIComponent(workspace)}`),
        api<Proposal[]>(`/v1/orgs/${orgId()}/operations/proposals?workspace_id=${encodeURIComponent(workspace)}`),
        api<ServiceOffering[]>(`/v1/orgs/${orgId()}/operations/service-catalog?workspace_id=${encodeURIComponent(workspace)}&status=active`),
      ]);
      setOpportunities(opps);
      setOfferings(catalogue);
      setServiceOfferingId(current => catalogue.some(item => item.id === current) ? current : "");
      setProposals(drafts);
      setOpportunityId(current => opps.some(item => item.id === current) ? current : opps[0]?.id || "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function createProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selectedOpportunity = opportunities.find(item => item.id === opportunityId);
    const numericAmount = Number(amount);
    if (!workspace || !selectedOpportunity || title.trim().length < 3 || !Number.isFinite(numericAmount) || numericAmount < 0) return;
    setSaving(true);
    setError("");
    try {
      await api<Proposal>(`/v1/orgs/${orgId()}/operations/proposals`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          opportunity_id: opportunityId,
          service_offering_id: serviceOfferingId || null,
          title: title.trim(),
          service_line: serviceLine.trim(),
          scope_summary: scope.trim(),
          deliverables: lines(deliverables),
          assumptions: lines(assumptions),
          exclusions: lines(exclusions),
          amount_minor: Math.round(numericAmount * 100),
          currency: selectedOpportunity.currency,
          validity_days: Number(validity),
        }),
      });
      setTitle(""); setServiceLine(""); setScope(""); setDeliverables(""); setAssumptions(""); setExclusions(""); setAmount("");
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function action(item: Proposal, kind: "submit" | "approve" | "reject") {
    setBusyId(item.id);
    setError("");
    try {
      const suffix = kind === "submit" ? "submit-for-approval" : kind;
      const payload = kind === "approve"
        ? { approval_id: item.approval_id, note: "Founder-approved proposal pricing" }
        : kind === "reject"
          ? { approval_id: item.approval_id, note: "Proposal requires revision" }
          : undefined;
      await api<Proposal>(`/v1/orgs/${orgId()}/operations/proposals/${item.id}/${suffix}`, {
        method: "POST",
        ...(payload ? { body: JSON.stringify(payload) } : {}),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  return (
    <Page eyebrow="REVENUE ENGINE" title="Proposals & commercial review" description="Prepare scoped proposal drafts against opportunities and route pricing through your explicit Founder Authority approval.">
      <Notice>These are internal proposal drafts. Approval does not send an email, create a contract, bind the agency, issue an invoice or start delivery. External delivery and contract execution remain separate approval-gated workflows.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Create proposal draft</h2>
        <form onSubmit={createProposal} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10,marginBottom:22}}>
          <select className="field" value={serviceOfferingId} onChange={e => {
            const selected = offerings.find(item => item.id === e.target.value);
            setServiceOfferingId(e.target.value);
            if (selected) {
              setServiceLine(selected.service_line);
              if (!scope.trim()) setScope(selected.description);
              if (!deliverables.trim()) setDeliverables(selected.deliverables.join("\\n"));
              if (!exclusions.trim()) setExclusions(selected.exclusions.join("\\n"));
              if (selected.indicative_price_minor !== null) setAmount(String(selected.indicative_price_minor / 100));
            }
          }}>
            <option value="">No catalogue offering (custom scope)</option>
            {offerings.map(item => <option key={item.id} value={item.id}>{item.name} · v{item.version} · {item.code}</option>)}
          </select>
          <select className="field" value={opportunityId} onChange={e => setOpportunityId(e.target.value)} required>
            <option value="">Select opportunity</option>
            {opportunities.map(item => <option key={item.id} value={item.id}>{item.title} · {item.stage}</option>)}
          </select>
          <input className="field" value={title} onChange={e => setTitle(e.target.value)} placeholder="Proposal title" maxLength={240} minLength={3} required />
          <input className="field" value={serviceLine} onChange={e => setServiceLine(e.target.value)} placeholder="Service line" maxLength={120} required />
          <input className="field" type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder={`Proposed fee (${opportunities.find(item => item.id === opportunityId)?.currency || "currency"})`} min={0} step="0.01" required />
          <input className="field" type="number" value={validity} onChange={e => setValidity(e.target.value)} placeholder="Validity days" min={1} max={180} required />
          <textarea className="field" value={scope} onChange={e => setScope(e.target.value)} placeholder="Scope summary" maxLength={12000} minLength={10} rows={3} style={{gridColumn:"1 / -1"}} required />
          <textarea className="field" value={deliverables} onChange={e => setDeliverables(e.target.value)} placeholder="Deliverables (one per line)" maxLength={6000} rows={3} />
          <textarea className="field" value={assumptions} onChange={e => setAssumptions(e.target.value)} placeholder="Assumptions (one per line)" maxLength={6000} rows={3} />
          <textarea className="field" value={exclusions} onChange={e => setExclusions(e.target.value)} placeholder="Exclusions (one per line)" maxLength={6000} rows={3} />
          <button className="button primary" type="submit" disabled={saving || !workspace || !opportunityId}>{saving ? "Saving…" : "Save draft"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Proposal register <span className="activity-meta">({proposals.length})</span></div>
          <button className="button secondary" type="button" onClick={() => void loadData()}>Refresh</button>
        </div>
        {loading ? <div className="empty">Loading proposals…</div> : proposals.length ? (
          <div className="activity">
            {proposals.map(item => (
              <div className="activity-row" key={item.id} style={{alignItems:"flex-start"}}>
                <span className="activity-dot" />
                <div style={{minWidth:0,width:"100%"}}>
                  <div className="activity-title">{item.title}</div>
                  <div className="activity-meta">{item.service_line} · {money(item.amount_minor,item.currency)} · {item.validity_days}-day validity · {item.status.replace("_"," ")}</div>
                  {item.service_offering_snapshot && <div className="activity-meta">Catalogue snapshot: {String(item.service_offering_snapshot.name || "Offering")} · v{String(item.service_offering_snapshot.version || "?")} (retained with this proposal)</div>}
                  <p className="activity-meta" style={{whiteSpace:"pre-wrap"}}>{item.scope_summary}</p>
                  {item.deliverables.length>0 && <div className="activity-meta">Deliverables: {item.deliverables.join(" · ")}</div>}
                  {item.approval_id && <div className="activity-meta">Approval reference: {item.approval_id}</div>}
                  {item.status === "pending_approval" && <Link href="/approvals" className="activity-meta">Review this request in the founder approvals queue</Link>}
                  {item.status === "draft" && <button className="button secondary" type="button" onClick={() => void action(item,"submit")} disabled={busyId===item.id}>{busyId===item.id ? "Submitting…" : "Request founder pricing approval"}</button>}
                  {item.status === "pending_approval" && <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                    <button className="button primary" type="button" onClick={() => void action(item,"approve")} disabled={busyId===item.id}>{busyId===item.id ? "Processing…" : "Finalize approved pricing"}</button>
                    <button className="button secondary" type="button" onClick={() => void action(item,"reject")} disabled={busyId===item.id}>Reject proposal</button>
                  </div>}
                  {item.status === "approved" && <div className="activity-meta">Founder-approved draft · Not sent to client</div>}
                </div>
              </div>
            ))}
          </div>
        ) : <div className="empty"><strong>No proposal drafts yet</strong>Create a draft from a qualified opportunity. Pricing remains internal until the founder approves it.</div>}
      </section>
    </Page>
  );
}
