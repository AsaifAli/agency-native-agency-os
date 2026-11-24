"use client";

import { useCallback, useEffect, useState, FormEvent } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Contract = { id:string; contract_number:string; title:string; status:string; terms_snapshot:Record<string,unknown>; };
type Onboarding = { id:string; contract_id:string; project_id:string|null; status:string; project_name:string; };
type Period = { id:string; contract_id:string; project_id:string; period_number:number; starts_at:string; ends_at:string; included_hours:number; rollover_in_hours:number; used_minutes:number; overage_minutes:number; status:string; closed_at:string|null; };
const dateValue = (value:string) => value ? new Date(value).toISOString().slice(0,10) : "";

export default function RetainersPage() {
  const [workspaces,setWorkspaces]=useState<Workspace[]>([]);
  const [workspace,setWorkspace]=useState("");
  const [contracts,setContracts]=useState<Contract[]>([]);
  const [onboardings,setOnboardings]=useState<Onboarding[]>([]);
  const [periods,setPeriods]=useState<Period[]>([]);
  const [onboardingId,setOnboardingId]=useState("");
  const [startsAt,setStartsAt]=useState("");
  const [endsAt,setEndsAt]=useState("");
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [busyId,setBusyId]=useState("");

  useEffect(()=>{ async function init(){ try { if(!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local."); const rows=await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`); setWorkspaces(rows); if(rows[0]) setWorkspace(rows[0].id); else setLoading(false); } catch(e){setError((e as Error).message);setLoading(false);} } void init(); },[]);

  const load=useCallback(async()=>{
    if(!workspace||!orgId()) return;
    setLoading(true);setError("");
    try{
      const [cs,os,ps]=await Promise.all([
        api<Contract[]>(`/v1/orgs/${orgId()}/operations/contracts?workspace_id=${encodeURIComponent(workspace)}`),
        api<Onboarding[]>(`/v1/orgs/${orgId()}/operations/onboardings?workspace_id=${encodeURIComponent(workspace)}`),
        api<Period[]>(`/v1/orgs/${orgId()}/operations/retainer-periods?workspace_id=${encodeURIComponent(workspace)}`),
      ]);
      setContracts(cs);setOnboardings(os);setPeriods(ps);
      const eligible=os.filter(o=>o.status==="active"&&!!o.project_id&&cs.some(c=>c.id===o.contract_id&&c.status==="executed"&&c.terms_snapshot.engagement_type==="retainer"));
      setOnboardingId(current=>eligible.some(o=>o.id===current)?current:eligible[0]?.id||"");
    }catch(e){setError((e as Error).message);}
    finally{setLoading(false);}
  },[workspace]);
  useEffect(()=>{void load();},[load]);

  const selected=onboardings.find(o=>o.id===onboardingId);
  const contract=selected?contracts.find(c=>c.id===selected.contract_id):undefined;
  const existing=selected?periods.filter(p=>p.contract_id===selected.contract_id).sort((a,b)=>a.period_number-b.period_number):[];
  const nextNumber=existing.length+1;
  const periodCount=Number(contract?.terms_snapshot.billing_period_count||0);
  const frequency=String(contract?.terms_snapshot.billing_frequency||"");
  const allowance=Number(contract?.terms_snapshot.included_hours_per_period||0);

  useEffect(()=>{
    if(!selected) return;
    const last=existing[existing.length-1];
    if(last){setStartsAt(dateValue(last.ends_at));}
  },[onboardingId,periods]);

  async function createPeriod(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!selected?.project_id||!contract||!startsAt||!endsAt)return;
    setSaving(true);setError("");
    try{
      await api<Period>(`/v1/orgs/${orgId()}/operations/retainer-periods`,{
        method:"POST",
        body:JSON.stringify({
          workspace_id:workspace,contract_id:contract.id,project_id:selected.project_id,
          period_number:nextNumber,starts_at:new Date(`${startsAt}T00:00:00`).toISOString(),
          ends_at:new Date(`${endsAt}T00:00:00`).toISOString(),
        }),
      });
      setEndsAt("");await load();
    }catch(e){setError((e as Error).message);}
    finally{setSaving(false);}
  }

  async function closePeriod(period:Period){
    setBusyId(period.id);setError("");
    try{await api<Period>(`/v1/orgs/${orgId()}/operations/retainer-periods/${period.id}/close`,{method:"POST"});await load();}
    catch(e){setError((e as Error).message);}
    finally{setBusyId("");}
  }

  return <Page eyebrow="DELIVERY & FINANCE" title="Retainer operations" description="Manage contracted service periods, included hours, usage snapshots and overage visibility.">
    <Notice>Period creation and closeout require Founder Authority. Usage is calculated from billable time entries. Overage is recorded for review only: this page does not approve extra charges, generate invoices, renew contracts or contact clients.</Notice>
    <section className="panel">
      <div className="panel-head"><div className="panel-title">Workspace</div><select className="field" value={workspace} onChange={e=>setWorkspace(e.target.value)}>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></div>
      {error&&<div className="error">{error}</div>}
      <h2 className="panel-title">Create next service period</h2>
      <form onSubmit={createPeriod} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10}}>
        <select className="field" value={onboardingId} onChange={e=>setOnboardingId(e.target.value)} required>
          <option value="">Select active retainer</option>
          {onboardings.filter(o=>o.status==="active"&&o.project_id&&contracts.some(c=>c.id===o.contract_id&&c.status==="executed"&&c.terms_snapshot.engagement_type==="retainer")).map(o=>{const c=contracts.find(x=>x.id===o.contract_id)!;return <option key={o.id} value={o.id}>{c.contract_number} · {o.project_name||c.title}</option>;})}
        </select>
        <input className="field" value={selected?String(nextNumber):""} readOnly aria-label="Next period number" placeholder="Period number"/>
        <input className="field" value={startsAt} onChange={e=>setStartsAt(e.target.value)} type="date" required/>
        <input className="field" value={endsAt} onChange={e=>setEndsAt(e.target.value)} type="date" required/>
        <button className="button primary" type="submit" disabled={saving||!selected||nextNumber>periodCount}>{saving?"Creating…":"Create service period"}</button>
      </form>
      {contract&&<p className="activity-meta">{frequency} billing · {periodCount} contracted periods · {allowance} included hours per period · Auto-renew: never executed automatically</p>}
      {selected&&nextNumber>periodCount&&<p className="activity-meta">All contracted service periods have been created.</p>}
    </section>
    <section className="panel">
      <h2 className="panel-title">Service period ledger</h2>
      {loading?<p className="activity-meta">Loading retainer records…</p>:periods.length===0?<p className="activity-meta">No retainer service periods have been created.</p>:periods.map(p=>{
        const c=contracts.find(x=>x.id===p.contract_id);
        const allowanceMinutes=(p.included_hours+p.rollover_in_hours)*60;
        return <div className="activity-row" key={p.id}>
          <span className="activity-dot"/>
          <div style={{flex:1}}>
            <div className="activity-title">{c?.contract_number||"Retainer"} · Period {p.period_number} · {p.status}</div>
            <p className="activity-meta">{new Date(p.starts_at).toLocaleDateString()} – {new Date(p.ends_at).toLocaleDateString()} · Allowance {p.included_hours+p.rollover_in_hours}h · Used {(p.used_minutes/60).toFixed(2)}h{p.status==="closed"?` · Overage ${(p.overage_minutes/60).toFixed(2)}h`:""}</p>
            {p.status==="open"&&<button className="button" type="button" disabled={!!busyId} onClick={()=>void closePeriod(p)}>{busyId===p.id?"Closing…":"Close period"}</button>}
            {p.status==="closed"&&<p className="activity-meta">Closed usage snapshot · {allowanceMinutes>0?Math.round(p.used_minutes/allowanceMinutes*100):0}% of allowance used</p>}
          </div>
        </div>;
      })}
    </section>
  </Page>;
}
