"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Contract = { id: string; contract_number: string; title: string; status: string; client_id: string; amount_minor: number; currency: string };
type Onboarding = {
  id: string; workspace_id: string; client_id: string; contract_id: string; project_id: string | null;
  status: string; approval_id: string | null; project_name: string; budget_minor: number;
  estimated_hours: number; due_date: string | null; activated_at: string | null;
};
type ChecklistItem = {
  id: string; onboarding_id: string; code: string; title: string; description: string;
  required: boolean; status: string; completion_note: string;
};
function money(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amount / 100);
}

export default function OnboardingPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [onboardings, setOnboardings] = useState<Onboarding[]>([]);
  const [selectedContract, setSelectedContract] = useState("");
  const [items, setItems] = useState<Record<string,ChecklistItem[]>>({});
  const [notes, setNotes] = useState<Record<string,string>>({});
  const [projectNames, setProjectNames] = useState<Record<string,string>>({});
  const [budgets, setBudgets] = useState<Record<string,string>>({});
  const [hours, setHours] = useState<Record<string,string>>({});
  const [dueDates, setDueDates] = useState<Record<string,string>>({});
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
    setLoading(true); setError("");
    try {
      const [contractRows, onboardingRows] = await Promise.all([
        api<Contract[]>(`/v1/orgs/${orgId()}/operations/contracts?workspace_id=${encodeURIComponent(workspace)}&status=executed`),
        api<Onboarding[]>(`/v1/orgs/${orgId()}/operations/onboardings?workspace_id=${encodeURIComponent(workspace)}`),
      ]);
      setContracts(contractRows);
      setOnboardings(onboardingRows);
      setSelectedContract(current => contractRows.some(item => item.id === current) ? current : contractRows[0]?.id || "");
      const checklistEntries = await Promise.all(onboardingRows.map(async item => {
        const rows = await api<ChecklistItem[]>(`/v1/orgs/${orgId()}/operations/onboardings/${item.id}/checklist`);
        return [item.id, rows] as const;
      }));
      setItems(Object.fromEntries(checklistEntries));
      setProjectNames(current => Object.fromEntries(onboardingRows.map(item => [item.id, current[item.id] || item.project_name || "Client delivery project"])));
      setBudgets(current => Object.fromEntries(onboardingRows.map(item => [item.id, current[item.id] ?? String(item.budget_minor / 100)])));
      setHours(current => Object.fromEntries(onboardingRows.map(item => [item.id, current[item.id] ?? String(item.estimated_hours || 80)])));
      setDueDates(current => Object.fromEntries(onboardingRows.map(item => [item.id, current[item.id] || (item.due_date ? item.due_date.slice(0,16) : "")])));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function createOnboarding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !selectedContract) return;
    setSaving(true); setError("");
    try {
      await api<Onboarding>(`/v1/orgs/${orgId()}/operations/onboardings`, {
        method: "POST", body: JSON.stringify({ workspace_id: workspace, contract_id: selectedContract }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function updateItem(onboarding: Onboarding, item: ChecklistItem, status: "open"|"completed"|"waived") {
    const note = (notes[item.id] || "").trim();
    if (status !== "open" && note.length < 3) {
      setError("Add a short evidence note; a waiver reason is required for Founder Authority.");
      return;
    }
    setBusyId(item.id); setError("");
    try {
      await api<ChecklistItem>(`/v1/orgs/${orgId()}/operations/onboardings/${onboarding.id}/checklist/${item.id}`, {
        method: "PATCH", body: JSON.stringify({ status, note }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function submitActivation(onboarding: Onboarding) {
    const budget = Number(budgets[onboarding.id] || 0);
    const estimate = Number(hours[onboarding.id] || 0);
    if (!projectNames[onboarding.id]?.trim() || !Number.isFinite(budget) || budget < 0 || !Number.isFinite(estimate) || estimate < 0) {
      setError("Enter a project name, valid budget and estimated hours.");
      return;
    }
    setBusyId(onboarding.id); setError("");
    try {
      await api<Onboarding>(`/v1/orgs/${orgId()}/operations/onboardings/${onboarding.id}/submit-for-activation`, {
        method: "POST",
        body: JSON.stringify({
          project_name: projectNames[onboarding.id].trim(),
          budget_minor: Math.round(budget * 100),
          estimated_hours: Math.round(estimate),
          due_date: dueDates[onboarding.id] ? new Date(dueDates[onboarding.id]).toISOString() : null,
        }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function rejectActivation(onboarding: Onboarding) {
    if (!onboarding.approval_id) return;
    setBusyId(onboarding.id); setError("");
    try {
      await api<Onboarding>(`/v1/orgs/${orgId()}/operations/onboardings/${onboarding.id}/reject-activation`, {
        method: "POST",
        body: JSON.stringify({ approval_id: onboarding.approval_id, note: "Founder requested onboarding readiness revision" }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function activate(onboarding: Onboarding) {
    setBusyId(onboarding.id); setError("");
    try {
      await api<Onboarding>(`/v1/orgs/${orgId()}/operations/onboardings/${onboarding.id}/activate`, { method: "POST" });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  return (
    <Page eyebrow="DELIVERY ENGINE" title="Client onboarding & delivery handoff" description="Start onboarding only from a recorded executed contract. Complete the readiness checklist, request founder approval and create the initial delivery project atomically.">
      <Notice>Creating onboarding never contacts the client. Checklist completion is an internal record. Delivery activation creates a planned project only after all required items are completed or explicitly waived by Founder Authority and the central <Link href="/approvals">delivery activation approval</Link> is approved.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Create client onboarding</h2>
        <form onSubmit={createOnboarding} style={{display:"grid",gridTemplateColumns:"minmax(240px,1fr) auto",gap:10,marginBottom:22}}>
          <select className="field" value={selectedContract} onChange={e => setSelectedContract(e.target.value)} required>
            <option value="">Select executed contract</option>
            {contracts.map(item => <option key={item.id} value={item.id}>{item.contract_number} · {item.title} · {money(item.amount_minor,item.currency)}</option>)}
          </select>
          <button className="button primary" type="submit" disabled={saving || !selectedContract}>{saving ? "Creating…" : "Create onboarding"}</button>
        </form>
        <div className="panel-head"><div className="panel-title">Client onboarding register <span className="activity-meta">({onboardings.length})</span></div><button className="button secondary" type="button" onClick={() => void loadData()}>Refresh</button></div>
        {loading ? <div className="empty">Loading onboarding records…</div> : onboardings.length ? (
          <div className="activity">
            {onboardings.map(onboarding => {
              const checklist = items[onboarding.id] || [];
              const requiredOpen = checklist.filter(item => item.required && item.status === "open").length;
              return (
                <div className="activity-row" key={onboarding.id} style={{alignItems:"flex-start"}}>
                  <span className="activity-dot" />
                  <div style={{minWidth:0,width:"100%"}}>
                    <div className="activity-title">{onboarding.project_name || "Client onboarding"}</div>
                    <div className="activity-meta">Client {onboarding.client_id} · Contract {onboarding.contract_id} · {onboarding.status.replace("_"," ")}</div>
                    <div className="activity-meta">{checklist.filter(item => item.status !== "open").length}/{checklist.length} checklist items resolved · {requiredOpen} required items remaining</div>
                    {checklist.map(item => (
                      <div key={item.id} style={{borderTop:"1px solid var(--border)",padding:"10px 0",marginTop:8}}>
                        <div className="activity-title">{item.title} {item.required ? "· Required" : "· Optional"} · {item.status}</div>
                        <div className="activity-meta">{item.description}</div>
                        {onboarding.status === "preparing" && <div style={{display:"grid",gridTemplateColumns:"minmax(180px,1fr) auto auto",gap:8,marginTop:8}}>
                          <input className="field" value={notes[item.id] ?? item.completion_note} onChange={e => setNotes(v => ({...v,[item.id]:e.target.value}))} placeholder="Evidence / waiver note" maxLength={2000} />
                          <button className="button secondary" type="button" onClick={() => void updateItem(onboarding,item,"completed")} disabled={busyId===item.id}>{busyId===item.id ? "Saving…" : "Complete"}</button>
                          <button className="button secondary" type="button" onClick={() => void updateItem(onboarding,item,"waived")} disabled={busyId===item.id}>Founder waiver</button>
                        </div>}
                      </div>
                    ))}
                    {onboarding.status === "preparing" && <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:8,marginTop:12}}>
                      <input className="field" value={projectNames[onboarding.id] || ""} onChange={e => setProjectNames(v => ({...v,[onboarding.id]:e.target.value}))} placeholder="Delivery project name" maxLength={240} />
                      <input className="field" type="number" value={budgets[onboarding.id] || ""} onChange={e => setBudgets(v => ({...v,[onboarding.id]:e.target.value}))} placeholder={`Internal project budget (${contracts.find(item => item.id === onboarding.contract_id)?.currency || "currency"})`} min={0} step="0.01" />
                      <input className="field" type="number" value={hours[onboarding.id] || ""} onChange={e => setHours(v => ({...v,[onboarding.id]:e.target.value}))} placeholder="Estimated hours" min={0} max={100000} />
                      <input className="field" type="datetime-local" value={dueDates[onboarding.id] || ""} onChange={e => setDueDates(v => ({...v,[onboarding.id]:e.target.value}))} />
                      <button className="button primary" type="button" onClick={() => void submitActivation(onboarding)} disabled={busyId===onboarding.id || requiredOpen>0}>{busyId===onboarding.id ? "Submitting…" : "Submit delivery activation"}</button>
                    </div>}
                    {onboarding.status === "pending_approval" && <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:10}}>
                      <Link href="/approvals" className="activity-meta">Review delivery activation in Founder Approvals</Link>
                      <button className="button primary" type="button" onClick={() => void activate(onboarding)} disabled={busyId===onboarding.id}>{busyId===onboarding.id ? "Activating…" : "Activate after approval"}</button>
                      <button className="button secondary" type="button" onClick={() => void rejectActivation(onboarding)} disabled={busyId===onboarding.id}>Reject / return to preparation</button>
                    </div>}
                    {onboarding.status === "active" && <div className="activity-meta">Delivery project created: {onboarding.project_id}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        ) : <div className="empty"><strong>No onboarding records</strong>Record a signed contract before creating the client onboarding handoff.</div>}
      </section>
    </Page>
  );
}
