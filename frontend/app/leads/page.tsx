"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Lead = {
  id: string;
  workspace_id: string;
  client_id: string | null;
  contact_id: string | null;
  company_name: string;
  contact_name: string;
  email: string;
  source: string;
  stage: string;
  score: number;
  qualification_notes: string;
  suppression_reason: string;
  created_at: string;
};

const stages = ["new", "researching", "qualified", "unqualified", "converted", "suppressed"];

export default function LeadsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [company, setCompany] = useState("");
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [source, setSource] = useState("");
  const [score, setScore] = useState("0");
  const [notes, setNotes] = useState("");
  const [stageDrafts, setStageDrafts] = useState<Record<string,string>>({});
  const [suppressionDrafts, setSuppressionDrafts] = useState<Record<string,string>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingLead, setSavingLead] = useState("");

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

  const loadLeads = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true);
    setError("");
    try {
      const rows = await api<Lead[]>(
        `/v1/orgs/${orgId()}/leads?workspace_id=${encodeURIComponent(workspace)}`
      );
      setLeads(rows);
      setStageDrafts(Object.fromEntries(rows.map(row => [row.id, row.stage])));
      setSuppressionDrafts(Object.fromEntries(rows.map(row => [row.id, row.suppression_reason || ""])));
    } catch (e) {
      setError((e as Error).message);
      setLeads([]);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadLeads(); }, [loadLeads]);

  async function createLead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || company.trim().length < 2) return;
    setSaving(true);
    setError("");
    try {
      await api<Lead>(`/v1/orgs/${orgId()}/leads`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          company_name: company.trim(),
          contact_name: contactName.trim(),
          email: email.trim(),
          source: source.trim(),
          score: Math.max(0, Math.min(100, Number(score) || 0)),
          qualification_notes: notes.trim(),
        }),
      });
      setCompany(""); setContactName(""); setEmail(""); setSource(""); setScore("0"); setNotes("");
      await loadLeads();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function updateStage(lead: Lead) {
    const stage = stageDrafts[lead.id] || lead.stage;
    const suppression_reason = suppressionDrafts[lead.id] || "";
    if (stage === "suppressed" && !suppression_reason.trim()) {
      setError("A suppression reason is required before suppressing a lead.");
      return;
    }
    setSavingLead(lead.id);
    setError("");
    try {
      await api<Lead>(`/v1/orgs/${orgId()}/leads/${lead.id}`, {
        method: "PATCH",
        body: JSON.stringify({ stage, suppression_reason }),
      });
      await loadLeads();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSavingLead("");
    }
  }

  return (
    <Page eyebrow="REVENUE ENGINE" title="Lead pipeline" description="Capture prospects, track qualification and maintain suppression decisions in the agency CRM. Research and communication remain separate governed actions.">
      <Notice>Creating or qualifying a lead does not send outreach, initiate calls, or create an opportunity automatically. Suppressed leads are blocked from outbound call queueing.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={event => setWorkspace(event.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Add prospect</h2>
        <form onSubmit={createLead} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10,marginBottom:22}}>
          <input className="field" value={company} onChange={e => setCompany(e.target.value)} placeholder="Company name" maxLength={200} minLength={2} required />
          <input className="field" value={contactName} onChange={e => setContactName(e.target.value)} placeholder="Contact name" maxLength={200} />
          <input className="field" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Business email" maxLength={320} />
          <input className="field" value={source} onChange={e => setSource(e.target.value)} placeholder="Lead source" maxLength={120} />
          <input className="field" type="number" value={score} onChange={e => setScore(e.target.value)} placeholder="Score 0–100" min={0} max={100} />
          <textarea className="field" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Qualification notes and evidence" maxLength={10000} rows={2} style={{gridColumn:"1 / -1"}} />
          <button className="button primary" type="submit" disabled={saving || !workspace}>{saving ? "Saving…" : "Add prospect"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Pipeline records <span className="activity-meta">({leads.length})</span></div>
          <button className="button secondary" type="button" onClick={() => void loadLeads()}>Refresh</button>
        </div>
        {loading ? <div className="empty">Loading pipeline…</div> : leads.length ? (
          <div className="activity">
            {leads.map(lead => (
              <div className="activity-row" key={lead.id} style={{alignItems:"flex-start"}}>
                <span className="activity-dot" />
                <div style={{minWidth:0,width:"100%"}}>
                  <div className="activity-title">{lead.company_name}</div>
                  <div className="activity-meta">{lead.contact_name || "Contact not recorded"} · {lead.email || "No email"} · Source: {lead.source || "Unspecified"} · Score: {lead.score}/100</div>
                  {lead.qualification_notes && <p className="activity-meta" style={{whiteSpace:"pre-wrap"}}>{lead.qualification_notes}</p>}
                  <div style={{display:"grid",gridTemplateColumns:"minmax(140px,180px) minmax(180px,1fr) auto",gap:8,marginTop:10}}>
                    <select className="field" value={stageDrafts[lead.id] || lead.stage} onChange={e => setStageDrafts(current => ({...current,[lead.id]:e.target.value}))}>
                      {stages.map(stage => <option key={stage} value={stage}>{stage.replace("_"," ")}</option>)}
                    </select>
                    {(stageDrafts[lead.id] || lead.stage) === "suppressed" && <input className="field" value={suppressionDrafts[lead.id] || ""} onChange={e => setSuppressionDrafts(current => ({...current,[lead.id]:e.target.value}))} placeholder="Required suppression reason" maxLength={240} />}
                    <button className="button secondary" type="button" onClick={() => void updateStage(lead)} disabled={savingLead===lead.id}>{savingLead===lead.id ? "Saving…" : "Save stage"}</button>
                  </div>
                  {lead.suppression_reason && <div className="activity-meta">Suppression reason: {lead.suppression_reason}</div>}
                </div>
              </div>
            ))}
          </div>
        ) : <div className="empty"><strong>No prospects yet</strong>Add a prospect manually or connect an approved lead source later. No lead data is fabricated or imported automatically.</div>}
      </section>
    </Page>
  );
}
