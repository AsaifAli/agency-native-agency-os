"use client";
import {useEffect,useState} from "react";
import Page from "@/components/page";
import {api,orgId} from "@/lib/api";
type Workspace={id:string;name:string};
type Approval={id:string;workspace_id:string;action_type:string;resource_id:string;status:string;requested_by:string;decision_note:string;created_at:string;request_payload:Record<string,unknown>};
export default function Approvals(){
 const [items,setItems]=useState<Approval[]>([]),[ws,setWs]=useState<Workspace[]>([]),[workspace,setWorkspace]=useState(""),[action,setAction]=useState("production.release"),[resource,setResource]=useState("release-candidate"),[reason,setReason]=useState(""),[err,setErr]=useState(""),[ok,setOk]=useState("");
 async function load(){const w=await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);setWs(w);const selected=workspace&&w.some(x=>x.id===workspace)?workspace:(w[0]?.id||"");if(selected){setWorkspace(selected);setItems(await api<Approval[]>(`/v1/orgs/${orgId()}/approvals?workspace_id=${encodeURIComponent(selected)}`))}else{setWorkspace("");setItems([])}}
 useEffect(()=>{if(orgId())load().catch(e=>setErr(e.message));else setErr("Set NEXT_PUBLIC_ORG_ID first.")},[]);
 async function request(){setErr("");setOk("");try{await api(`/v1/orgs/${orgId()}/approvals`,{method:"POST",body:JSON.stringify({workspace_id:workspace,action_type:action,resource_id:resource,idempotency_key:crypto.randomUUID(),request_payload:{reason}})});setOk("Approval request recorded.");await load()}catch(e){setErr((e as Error).message)}}
 async function decide(id:string,decision:"approved"|"rejected"){setErr("");setOk("");try{await api(`/v1/orgs/${orgId()}/approvals/${id}/decision?workspace_id=${encodeURIComponent(workspace)}`,{method:"POST",body:JSON.stringify({decision,note:"Reviewed in founder console"})});setOk(`Request ${decision}.`);await load()}catch(e){setErr((e as Error).message)}}
 return <Page eyebrow="FOUNDER GOVERNANCE" title="Approvals" description="Review high-impact actions before execution.">
 <div className="notice">Only a user with explicit Founder Authority can approve or reject requests. Founder Authority is separate from organization-owner permissions. Protected action handlers must consume approvals atomically before side effects.</div>
 <div className="panel"><div className="panel-head"><div className="panel-title">Request approval</div></div><div className="form-grid">
 <label>Action<select className="field" value={action} onChange={e=>setAction(e.target.value)}>{["contract.execute","delivery.activate","invoice.issue","pricing.change","payment.issue","external_communication.sensitive","production.release","resource.delete","client_data.delete","security.permission.change"].map(x=><option key={x}>{x}</option>)}</select></label>
 <label>Workspace<select className="field" value={workspace} onChange={e=>{const next=e.target.value;setWorkspace(next);api<Approval[]>(`/v1/orgs/${orgId()}/approvals?workspace_id=${encodeURIComponent(next)}`).then(setItems).catch(error=>setErr(error.message))}}>{ws.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
 <label>Resource ID<input className="field" value={resource} onChange={e=>setResource(e.target.value)}/></label><label>Reason<input className="field" value={reason} onChange={e=>setReason(e.target.value)}/></label>
 </div><div style={{marginTop:13}}><button className="button" onClick={request} disabled={!workspace||!resource.trim()}>Submit approval request</button></div>
 {err&&<div className="error">{err}</div>}{ok&&<div className="success">{ok}</div>}</div>
 <div style={{height:16}}/><div className="panel"><div className="panel-head"><div className="panel-title">Approval queue</div><span className="panel-note">{items.length} records</span><button className="button secondary" onClick={()=>load().catch(e=>setErr(e.message))} disabled={!workspace}>Refresh</button></div>
 <div className="table-wrap"><table className="data-table"><thead><tr><th>Action</th><th>Resource</th><th>Status</th><th>Requested</th><th>Decision</th></tr></thead><tbody>{items.map(a=><tr key={a.id}><td>{a.action_type}</td><td>{a.resource_id}</td><td><span className={`status ${a.status}`}>{a.status}</span></td><td>{new Date(a.created_at).toLocaleString()}</td><td>{a.status==="pending"?<div style={{display:"flex",gap:6}}><button className="button" onClick={()=>decide(a.id,"approved")}>Approve</button><button className="button secondary" onClick={()=>decide(a.id,"rejected")}>Reject</button></div>:a.decision_note||"—"}</td></tr>)}</tbody></table></div>
 {!items.length&&<div className="empty">No approval requests yet.</div>}</div></Page>
}
