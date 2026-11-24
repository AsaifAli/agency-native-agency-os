"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Opportunity = { id: string; title: string; client_id: string | null; currency: string };
type Proposal = { id: string; title: string; status: string; amount_minor: number; currency: string; opportunity_id: string };
type Contract = {
  id: string;
  workspace_id: string;
  client_id: string;
  proposal_id: string;
  contract_number: string;
  title: string;
  amount_minor: number;
  currency: string;
  terms_snapshot: Record<string, unknown>;
  status: string;
  approval_id: string | null;
  signed_reference: string;
  signed_at: string | null;
  executed_by: string | null;
  executed_at: string | null;
  created_at: string;
};
function money(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amount / 100);
}

export default function ContractsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [proposalId, setProposalId] = useState("");
  const [contractNumber, setContractNumber] = useState("");
  const [title, setTitle] = useState("");
  const [signedRefs, setSignedRefs] = useState<Record<string,string>>({});
  const [signedDates, setSignedDates] = useState<Record<string,string>>({});
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
      const [contractRows, proposalRows, opportunityRows] = await Promise.all([
        api<Contract[]>(`/v1/orgs/${orgId()}/operations/contracts?workspace_id=${encodeURIComponent(workspace)}`),
        api<Proposal[]>(`/v1/orgs/${orgId()}/operations/proposals?workspace_id=${encodeURIComponent(workspace)}`),
        api<Opportunity[]>(`/v1/orgs/${orgId()}/opportunities?workspace_id=${encodeURIComponent(workspace)}`),
      ]);
      setContracts(contractRows);
      setProposals(proposalRows);
      setOpportunities(opportunityRows);
      const eligible = proposalRows.filter(p => p.status === "approved" && opportunityRows.some(o => o.id === p.opportunity_id && !!o.client_id));
      setProposalId(current => eligible.some(p => p.id === current) ? current : eligible[0]?.id || "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function createContract(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !proposalId || contractNumber.trim().length < 2 || title.trim().length < 3) return;
    setSaving(true);
    setError("");
    try {
      await api<Contract>(`/v1/orgs/${orgId()}/operations/contracts`, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspace, proposal_id: proposalId, contract_number: contractNumber.trim(), title: title.trim() }),
      });
      setContractNumber(""); setTitle("");
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function submitForApproval(item: Contract) {
    setBusyId(item.id); setError("");
    try {
      await api<Contract>(`/v1/orgs/${orgId()}/operations/contracts/${item.id}/submit-for-approval`, { method: "POST" });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function rejectContract(item: Contract) {
    if (!item.approval_id) return;
    setBusyId(item.id); setError("");
    try {
      await api<Contract>(`/v1/orgs/${orgId()}/operations/contracts/${item.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ approval_id: item.approval_id, note: "Founder rejected contract execution" }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function recordExecution(item: Contract) {
    const reference = (signedRefs[item.id] || "").trim();
    const date = signedDates[item.id];
    if (!item.approval_id || reference.length < 3 || !date) {
      setError("Enter the signed agreement reference and signing date before recording execution.");
      return;
    }
    setBusyId(item.id); setError("");
    try {
      await api<Contract>(`/v1/orgs/${orgId()}/operations/contracts/${item.id}/record-execution`, {
        method: "POST",
        body: JSON.stringify({ approval_id: item.approval_id, signed_reference: reference, signed_at: new Date(date).toISOString() }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  return (
    <Page eyebrow="REVENUE ENGINE" title="Contract register" description="Track agreements derived from founder-approved proposals. Contract execution requires Founder Authority approval and evidence that the agreement has actually been signed.">
      <Notice>This register does not generate legal advice, send contracts, collect signatures or create a legally binding agreement. Record execution only after signing has occurred outside the OS and the signed copy/reference is available. Approval requests are reviewed in the central <Link href="/approvals">Founder Approvals queue</Link>.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Register contract draft</h2>
        <form onSubmit={createContract} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10,marginBottom:22}}>
          <select className="field" value={proposalId} onChange={e => setProposalId(e.target.value)} required>
            <option value="">Select approved proposal linked to a client</option>
            {proposals.filter(p => p.status === "approved" && opportunities.some(o => o.id === p.opportunity_id && !!o.client_id)).map(p => <option key={p.id} value={p.id}>{p.title} · {money(p.amount_minor,p.currency)}</option>)}
          </select>
          <input className="field" value={contractNumber} onChange={e => setContractNumber(e.target.value)} placeholder="Contract number / reference" maxLength={80} required />
          <input className="field" value={title} onChange={e => setTitle(e.target.value)} placeholder="Agreement title" maxLength={240} minLength={3} required />
          <button className="button primary" type="submit" disabled={saving || !proposalId}>{saving ? "Saving…" : "Create contract record"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Contract register <span className="activity-meta">({contracts.length})</span></div>
          <button className="button secondary" type="button" onClick={() => void loadData()}>Refresh</button>
        </div>
        {loading ? <div className="empty">Loading contracts…</div> : contracts.length ? (
          <div className="activity">
            {contracts.map(item => (
              <div className="activity-row" key={item.id} style={{alignItems:"flex-start"}}>
                <span className="activity-dot" />
                <div style={{minWidth:0,width:"100%"}}>
                  <div className="activity-title">{item.title}</div>
                  <div className="activity-meta">{item.contract_number} · {money(item.amount_minor,item.currency)} · {item.status.replace("_"," ")}</div>
                  <div className="activity-meta">Client record: {item.client_id} · Proposal: {item.proposal_id}</div>
                  {item.status === "draft" && <button className="button secondary" type="button" onClick={() => void submitForApproval(item)} disabled={busyId===item.id}>{busyId===item.id ? "Submitting…" : "Request contract execution approval"}</button>}
                  {item.status === "pending_approval" && <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:8,marginTop:10}}>
                    <input className="field" value={signedRefs[item.id] || ""} onChange={e => setSignedRefs(v => ({...v,[item.id]:e.target.value}))} placeholder="Signed copy reference / storage ID" maxLength={240} />
                    <input className="field" type="datetime-local" value={signedDates[item.id] || ""} onChange={e => setSignedDates(v => ({...v,[item.id]:e.target.value}))} />
                    <button className="button primary" type="button" onClick={() => void recordExecution(item)} disabled={busyId===item.id || !item.approval_id}>{busyId===item.id ? "Recording…" : "Record signed execution"}</button>
                    <Link href="/approvals" className="activity-meta">Approve contract execution in Founder Approvals</Link>
                    <button className="button secondary" type="button" onClick={() => void rejectContract(item)} disabled={busyId===item.id}>{busyId===item.id ? "Rejecting…" : "Reject contract"}</button>
                  </div>}
                  {item.status === "executed" && <div className="activity-meta">Signed reference: {item.signed_reference} · Signed {item.signed_at ? new Date(item.signed_at).toLocaleString() : "date not recorded"}</div>}
                  {item.approval_id && <div className="activity-meta">Approval ID: {item.approval_id}</div>}
                </div>
              </div>
            ))}
          </div>
        ) : <div className="empty"><strong>No contract records yet</strong>Only approved proposals associated with a client can be registered as contracts.</div>}
      </section>
    </Page>
  );
}
