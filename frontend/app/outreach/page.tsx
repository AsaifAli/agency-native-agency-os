"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Lead = { id: string; company_name: string; contact_name: string; email: string; stage: string; };
type Research = { id: string; lead_id: string; summary: string; fit_score: number; confidence_score: number; buying_signals: string[]; risks: string[]; source_references: {label:string;url:string;accessed_at:string}[]; researched_at: string; };
type Draft = { id: string; lead_id: string; channel: string; subject: string; body: string; status: string; review_note: string; created_at: string; };

export default function OutreachPage() {
  const [workspaces,setWorkspaces] = useState<Workspace[]>([]);
  const [workspace,setWorkspace] = useState("");
  const [leads,setLeads] = useState<Lead[]>([]);
  const [leadId,setLeadId] = useState("");
  const [research,setResearch] = useState<Research[]>([]);
  const [drafts,setDrafts] = useState<Draft[]>([]);
  const [summary,setSummary] = useState("");
  const [fitScore,setFitScore] = useState("50");
  const [confidence,setConfidence] = useState("50");
  const [sourceLabel,setSourceLabel] = useState("");
  const [sourceUrl,setSourceUrl] = useState("");
  const [buyingSignals,setBuyingSignals] = useState("");
  const [risks,setRisks] = useState("");
  const [channel,setChannel] = useState("email");
  const [subject,setSubject] = useState("");
  const [body,setBody] = useState("");
  const [basis,setBasis] = useState("");
  const [error,setError] = useState("");
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState(false);
  const [busyId,setBusyId] = useState("");

  useEffect(() => {
    async function init() {
      try {
        if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
        setWorkspaces(rows);
        if (rows[0]) setWorkspace(rows[0].id); else setLoading(false);
      } catch (e) { setError((e as Error).message); setLoading(false); }
    }
    void init();
  }, []);

  const load = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true); setError("");
    try {
      const [leadRows,draftRows] = await Promise.all([
        api<Lead[]>(`/v1/orgs/${orgId()}/leads?workspace_id=${encodeURIComponent(workspace)}`),
        api<Draft[]>(`/v1/orgs/${orgId()}/outreach-drafts?workspace_id=${encodeURIComponent(workspace)}`),
      ]);
      setLeads(leadRows);
      setDrafts(draftRows);
      setLeadId(current => leadRows.some(x => x.id === current) ? current : leadRows.find(x => x.stage !== "suppressed" && x.stage !== "unqualified")?.id || "");
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  },[workspace]);

  const loadResearch = useCallback(async () => {
    if (!workspace || !leadId || !orgId()) { setResearch([]); return; }
    try {
      const rows = await api<Research[]>(`/v1/orgs/${orgId()}/leads/${leadId}/research?workspace_id=${encodeURIComponent(workspace)}`);
      setResearch(rows);
    } catch (e) { setError((e as Error).message); }
  },[workspace,leadId]);

  useEffect(() => { void load(); },[load]);
  useEffect(() => { void loadResearch(); },[loadResearch]);

  async function addResearch(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!leadId || summary.trim().length < 20 || !sourceUrl.trim()) return;
    setSaving(true); setError("");
    try {
      await api<Research>(`/v1/orgs/${orgId()}/lead-research`,{
        method:"POST",
        body:JSON.stringify({
          workspace_id:workspace,lead_id:leadId,summary:summary.trim(),
          fit_score:Number(fitScore),confidence_score:Number(confidence),
          buying_signals:buyingSignals.split("\\n").map(x=>x.trim()).filter(Boolean),
          risks:risks.split("\\n").map(x=>x.trim()).filter(Boolean),
          source_references:[{label:sourceLabel.trim(),url:sourceUrl.trim(),accessed_at:new Date().toISOString()}],
        }),
      });
      setSummary("");setSourceLabel("");setSourceUrl("");setBuyingSignals("");setRisks("");
      await loadResearch();
    } catch(e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }

  async function createDraft(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!leadId || body.trim().length < 20) return;
    setSaving(true);setError("");
    try {
      await api<Draft>(`/v1/orgs/${orgId()}/outreach-drafts`,{
        method:"POST",
        body:JSON.stringify({
          workspace_id:workspace,lead_id:leadId,channel,subject:subject.trim(),
          body:body.trim(),personalization_basis:basis.trim(),
          source_research_ids:research.map(x=>x.id),
        }),
      });
      setSubject("");setBody("");setBasis("");
      await load();
    } catch(e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }

  async function reviewDraft(item:Draft,decision:"approve_draft"|"reject") {
    setBusyId(item.id);setError("");
    try {
      await api<Draft>(`/v1/orgs/${orgId()}/outreach-drafts/${item.id}/review`,{
        method:"POST",body:JSON.stringify({decision,note:decision==="approve_draft"?"Founder reviewed draft; dispatch remains separately gated.":"Needs revision."}),
      });
      await load();
    } catch(e) { setError((e as Error).message); }
    finally { setBusyId(""); }
  }

  const selectedLead = leads.find(x=>x.id===leadId);
  return (
    <Page eyebrow="REVENUE ENGINE" title="Research & outreach studio" description="Agent-prepared prospect intelligence and personalized communication drafts, with source evidence and founder review.">
      <Notice>Claude agents may research, qualify, personalize and draft. This workspace never sends, schedules or queues messages. Draft approval is not permission to dispatch. Suppressed leads cannot receive new research or outreach drafts.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace & prospect</div>
          <select className="field" value={workspace} onChange={e=>setWorkspace(e.target.value)}>{workspaces.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select>
          <select className="field" value={leadId} onChange={e=>setLeadId(e.target.value)}>
            <option value="">Select prospect</option>
            {leads.filter(x=>x.stage!=="suppressed"&&x.stage!=="unqualified").map(x=><option key={x.id} value={x.id}>{x.company_name} · {x.stage}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        {selectedLead && <div className="activity-meta">Prospect: {selectedLead.company_name} · {selectedLead.contact_name || "No contact"} · {selectedLead.email || "No email"}</div>}
      </section>
      <section className="panel">
        <h2 className="panel-title">Research evidence</h2>
        <form onSubmit={addResearch} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10}}>
          <input className="field" value={sourceLabel} onChange={e=>setSourceLabel(e.target.value)} placeholder="Source label" required />
          <input className="field" type="url" value={sourceUrl} onChange={e=>setSourceUrl(e.target.value)} placeholder="HTTPS source URL" required />
          <input className="field" type="number" value={fitScore} onChange={e=>setFitScore(e.target.value)} min={0} max={100} placeholder="Fit score" />
          <input className="field" type="number" value={confidence} onChange={e=>setConfidence(e.target.value)} min={0} max={100} placeholder="Confidence" />
          <textarea className="field" value={summary} onChange={e=>setSummary(e.target.value)} placeholder="Evidence-based research summary; distinguish facts from inference" minLength={20} maxLength={12000} rows={3} style={{gridColumn:"1 / -1"}} required />
          <textarea className="field" value={buyingSignals} onChange={e=>setBuyingSignals(e.target.value)} placeholder="Buying signals (one per line)" rows={2} />
          <textarea className="field" value={risks} onChange={e=>setRisks(e.target.value)} placeholder="Risks and unknowns (one per line)" rows={2} />
          <button className="button primary" type="submit" disabled={saving||!leadId}>{saving?"Saving…":"Record research"}</button>
        </form>
        <div className="activity">
          {research.map(x=><div className="activity-row" key={x.id}><span className="activity-dot"/><div><div className="activity-title">Fit {x.fit_score}/100 · Confidence {x.confidence_score}/100</div><p className="activity-meta">{x.summary}</p>{x.source_references.map(s=><a className="activity-meta" key={s.url} href={s.url} target="_blank" rel="noreferrer">{s.label}</a>)}</div></div>)}
          {!research.length&&!loading&&<div className="empty">No research evidence recorded for this prospect yet.</div>}
        </div>
      </section>
      <section className="panel">
        <h2 className="panel-title">Outreach draft</h2>
        <form onSubmit={createDraft} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10}}>
          <select className="field" value={channel} onChange={e=>setChannel(e.target.value)}><option value="email">Email</option><option value="linkedin">LinkedIn message</option><option value="call_script">Call script</option></select>
          <input className="field" value={subject} onChange={e=>setSubject(e.target.value)} placeholder="Subject (optional)" maxLength={240} />
          <textarea className="field" value={basis} onChange={e=>setBasis(e.target.value)} placeholder="Personalization basis and cited facts" rows={2} maxLength={6000} />
          <textarea className="field" value={body} onChange={e=>setBody(e.target.value)} placeholder="Draft content; no message is sent" rows={5} minLength={20} maxLength={12000} style={{gridColumn:"1 / -1"}} required />
          <button className="button primary" type="submit" disabled={saving||!leadId}>{saving?"Saving…":"Save outreach draft"}</button>
        </form>
        <div className="panel-head"><div className="panel-title">Draft review queue ({drafts.length})</div><button className="button secondary" type="button" onClick={()=>void load()}>Refresh</button></div>
        <div className="activity">
          {drafts.map(item=><div className="activity-row" key={item.id}><span className="activity-dot"/><div style={{width:"100%"}}><div className="activity-title">{item.subject||item.channel+" draft"} · {item.status.replace("_"," ")}</div><p className="activity-meta" style={{whiteSpace:"pre-wrap"}}>{item.body}</p>{item.status==="draft"&&<div style={{display:"flex",gap:8}}><button className="button primary" type="button" disabled={busyId===item.id} onClick={()=>void reviewDraft(item,"approve_draft")}>Approve draft</button><button className="button secondary" type="button" disabled={busyId===item.id} onClick={()=>void reviewDraft(item,"reject")}>Reject</button></div>}{item.status==="approved_draft"&&<div className="activity-meta">Founder-reviewed only. Not sent or scheduled.</div>}</div></div>)}
          {!drafts.length&&!loading&&<div className="empty">No outreach drafts yet. Agents can prepare them after research and qualification.</div>}
        </div>
      </section>
    </Page>
  );
}
