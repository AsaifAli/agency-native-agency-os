"use client";
import { useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";
type Brief={generated_at:string;signals:Record<string,number>;note:string};
type Knowledge={id:string;key:string;version:number;title:string;content:string;classification:string;status:string;source_reference:string};
type Draft={id:string;kind:string;status:string;source_refs:{type:string;id:string}[];content:Record<string,unknown>;created_at:string};
type Aging={invoices:{invoice_id:string;invoice_number:string;outstanding_minor:number;currency:string;days_overdue:number;bucket:string}[];currency_note:string};
type SourceOption={id:string;label:string};
type LearningCandidate={id:string;title:string;content:string;evidence_summary:string;source_type:string;source_reference:string;data_class:string;confidence:number;scope:string;status:string;knowledge_item_id:string|null};
type SourceExecution={id:string;runtime:string;task_id:string;data_class:string;finished_at:string|null;created_at:string};
const base=()=>"/v1/orgs/"+orgId();
export default function PrivateOperationsPage(){
 const [workspaces,setWorkspaces]=useState<Workspace[]>([]),[workspace,setWorkspace]=useState("");
 const [brief,setBrief]=useState<Brief|null>(null),[aging,setAging]=useState<Aging|null>(null),[knowledge,setKnowledge]=useState<Knowledge[]>([]),[drafts,setDrafts]=useState<Draft[]>([]),[learning,setLearning]=useState<LearningCandidate[]>([]),[sourceExecutions,setSourceExecutions]=useState<SourceExecution[]>([]);
 const [key,setKey]=useState(""),[title,setTitle]=useState(""),[content,setContent]=useState(""),[classification,setClassification]=useState("internal");
 const [kind,setKind]=useState("front_desk"),[sourceId,setSourceId]=useState(""),[draftContent,setDraftContent]=useState(""),[sourceOptions,setSourceOptions]=useState<SourceOption[]>([]);
 const [error,setError]=useState(""),[busy,setBusy]=useState(false);
 const [learningTitle,setLearningTitle]=useState(""),[learningContent,setLearningContent]=useState(""),[learningEvidence,setLearningEvidence]=useState(""),[learningSourceId,setLearningSourceId]=useState(""),[learningConfidence,setLearningConfidence]=useState("0.8");
 const load=useCallback(async(id:string)=>{if(!id)return;try{setError("");const [b,a,k,d,l,executions]=await Promise.all([
  api<Brief>(base()+"/founder-brief?workspace_id="+encodeURIComponent(id)),
  api<Aging>(base()+"/receivables/aging?workspace_id="+encodeURIComponent(id)),
  api<Knowledge[]>(base()+"/knowledge?workspace_id="+encodeURIComponent(id)),
  api<Draft[]>(base()+"/business-drafts?workspace_id="+encodeURIComponent(id)),
  api<LearningCandidate[]>(base()+"/learning/candidates?workspace_id="+encodeURIComponent(id)),
  api<SourceExecution[]>(base()+"/executions?workspace_id="+encodeURIComponent(id)+"&status=succeeded&limit=100")]);
  setBrief(b);setAging(a);setKnowledge(k);setDrafts(d);setLearning(l);setSourceExecutions(executions.filter(row=>["synthetic","public","internal"].includes(row.data_class)));setLearningSourceId(current=>executions.some(row=>row.id===current&&["synthetic","public","internal"].includes(row.data_class))?current:executions.find(row=>["synthetic","public","internal"].includes(row.data_class))?.id??"");
  const suffix="?workspace_id="+encodeURIComponent(id);
  const sourceRows=kind==="front_desk"
    ? await api<{id:string;company_name:string;stage:string}[]>(base()+"/leads"+suffix)
    : kind==="meeting_proposal"
      ? await api<{id:string;title:string;stage:string}[]>(base()+"/opportunities"+suffix)
      : await api<{id:string;invoice_number:string;status:string}[]>(base()+"/operations/invoices"+suffix);
  const options=sourceRows.map(row=>({id:row.id,label:"company_name" in row?row.company_name+" · "+row.stage:"invoice_number" in row?row.invoice_number+" · "+row.status:row.title+" · "+row.stage}));
  setSourceOptions(options);
  if(!options.some(option=>option.id===sourceId))setSourceId(options[0]?.id??"");
 }catch(e){setError((e as Error).message)}},[kind,sourceId])
 useEffect(()=>{async function init(){try{if(!orgId())throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");const rows=await api<Workspace[]>(base()+"/workspaces");setWorkspaces(rows);if(rows[0])setWorkspace(rows[0].id)}catch(e){setError((e as Error).message)}}void init()},[]);
 useEffect(()=>{void load(workspace)},[workspace,load]);
 async function run(action:()=>Promise<unknown>){setBusy(true);setError("");try{await action();await load(workspace)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function addKnowledge(){await run(async()=>{await api(base()+"/knowledge",{method:"POST",body:JSON.stringify({workspace_id:workspace,key,title,content,source_type:"founder_note",source_reference:"founder-console",classification})});setKey("");setTitle("");setContent("")})}
 async function addDraft(){await run(async()=>{const parsed=JSON.parse(draftContent||"{}");const sourceType=kind==="front_desk"?"lead":kind==="meeting_proposal"?"opportunity":"invoice";await api(base()+"/business-drafts",{method:"POST",body:JSON.stringify({workspace_id:workspace,kind,source_refs:[{type:sourceType,id:sourceId}],content:parsed})});setSourceId("");setDraftContent("")})}
 async function approve(id:string){await run(()=>api(base()+"/knowledge/"+id+"/approve",{method:"POST",body:JSON.stringify({workspace_id:workspace})}))}
 async function review(id:string,decision:"reviewed"|"rejected"){await run(()=>api(base()+"/business-drafts/"+id+"/review",{method:"POST",body:JSON.stringify({workspace_id:workspace,decision})}))}
 async function addLearning(){await run(async()=>{await api(base()+"/learning/candidates",{method:"POST",body:JSON.stringify({workspace_id:workspace,title:learningTitle,content:learningContent,evidence_summary:learningEvidence,source_type:"execution",source_reference:learningSourceId,confidence:Number(learningConfidence)})});setLearningTitle("");setLearningContent("");setLearningEvidence("")})}
 async function reviewLearning(id:string,decision:"approve"|"reject"){await run(()=>api(base()+"/learning/candidates/"+id+"/review",{method:"POST",body:JSON.stringify({workspace_id:workspace,decision})}))}
 return <Page eyebrow="FOUNDER INTELLIGENCE" title="Private operations" description="Governed knowledge, source-linked workflow drafts, receivables and a read-only founder brief.">
  <Notice>Agency OS owns business records and approvals. Drafts may be prepared by a human or authorized hosted Claude runtime. This page does not invoke a model, send communications, issue invoices or approve proposals. Knowledge retention policy is recorded as metadata; automated expiry and artifact cleanup still require the retention lifecycle integration.</Notice>
  <section className="panel"><div className="panel-head"><div className="panel-title">Workspace scope</div><select className="field" value={workspace} onChange={e=>setWorkspace(e.target.value)}>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></div>{error&&<div className="error">{error}</div>}</section>
  <div style={{height:16}}/>
  <section className="panel"><div className="panel-head"><div className="panel-title">Founder daily brief</div><span className="panel-note">{brief?new Date(brief.generated_at).toLocaleString():"Loading…"}</span></div>
   <div className="grid stats">{Object.entries(brief?.signals??{}).map(([name,value])=><div className="stat" key={name}><div className="stat-label">{name.replaceAll("_"," ")}</div><div className="stat-value">{value}</div><div className="stat-foot">Current workspace</div></div>)}</div><div className="activity-meta">{brief?.note}</div></section>
  <div style={{height:16}}/>
  <section className="panel"><div className="panel-head"><div className="panel-title">Receivables ageing</div><span className="panel-note">Outstanding by invoice currency</span></div><div className="activity-meta">{aging?.currency_note}</div>
   {aging?.invoices.length?<div className="activity">{aging.invoices.map(x=><div className="activity-row" key={x.invoice_id}><span className="activity-dot"/><div><div className="activity-title">{x.invoice_number} · {new Intl.NumberFormat(undefined,{style:"currency",currency:x.currency}).format(x.outstanding_minor/100)}</div><div className="activity-meta">{x.days_overdue} days overdue · {x.bucket.replaceAll("_"," ")}</div></div></div>)}</div>:<div className="empty">No issued invoices with outstanding balances.</div>}</section>
  <div style={{height:16}}/>
  <section className="panel"><div className="panel-head"><div className="panel-title">Agency learning review</div><span className="panel-note">{learning.filter(x=>x.status==="pending_review").length} awaiting founder review</span></div>
   <Notice>Lessons are captured from completed executions in this workspace. Source data classification is derived by the API; commercial, confidential and regulated source executions are blocked. Promotion is founder-only and remains workspace-scoped.</Notice>
   <div className="form-grid">
    <label>Completed execution source<select className="field" value={learningSourceId} onChange={e=>setLearningSourceId(e.target.value)}><option value="">Choose a completed execution</option>{sourceExecutions.map(x=><option key={x.id} value={x.id}>{x.runtime} · {x.data_class} · {x.id.slice(0,8)} · {new Date(x.finished_at??x.created_at).toLocaleString()}</option>)}</select></label>
    <label>Confidence (self-assessed, 0–1)<input className="field" type="number" min="0" max="1" step="0.05" value={learningConfidence} onChange={e=>setLearningConfidence(e.target.value)}/></label>
    <label className="wide">Lesson title<input className="field" value={learningTitle} onChange={e=>setLearningTitle(e.target.value)} placeholder="Require acceptance criteria before estimation"/></label>
    <label className="wide">Reusable lesson<textarea className="field" rows={3} value={learningContent} onChange={e=>setLearningContent(e.target.value)}/></label>
    <label className="wide">Evidence summary<textarea className="field" rows={2} value={learningEvidence} onChange={e=>setLearningEvidence(e.target.value)} placeholder="What did the source evaluation demonstrate?"/></label>
   </div>
   <button className="button" disabled={busy||!learningSourceId||!learningTitle.trim()||!learningContent.trim()||!learningEvidence.trim()||!Number.isFinite(Number(learningConfidence))||Number(learningConfidence)<0||Number(learningConfidence)>1} onClick={()=>void addLearning()}>Submit learning candidate</button>
   <div className="activity">{learning.map(x=><div className="activity-row" key={x.id}><span className={`status ${x.status==="promoted"?"success":x.status==="rejected"?"pending":""}`}>{x.status.replaceAll("_"," ")}</span><div style={{flex:1}}><div className="activity-title">{x.title}</div><div className="activity-meta">{x.source_type} · {x.data_class} · confidence {(x.confidence*100).toFixed(0)}% · {x.scope} scope</div><p>{x.content}</p><div className="activity-meta">Evidence: {x.evidence_summary}</div>{x.status==="pending_review"&&<div className="actions"><button className="button secondary" disabled={busy} onClick={()=>void reviewLearning(x.id,"approve")}>Promote as founder</button><button className="button secondary" disabled={busy} onClick={()=>void reviewLearning(x.id,"reject")}>Reject</button></div>}</div></div>)}</div>
   {!learning.length&&<div className="empty">No learning candidates yet. Submit an evidence-backed lesson from a completed execution.</div>}
  </section>
  <div style={{height:16}}/>
  <div className="two-col">
   <section className="panel"><div className="panel-head"><div className="panel-title">Governed knowledge</div><span className="panel-note">{knowledge.length} versions</span></div>
    <div className="form-grid"><label>Knowledge key<input className="field" value={key} onChange={e=>setKey(e.target.value)} placeholder="delivery.playbook"/></label><label>Title<input className="field" value={title} onChange={e=>setTitle(e.target.value)}/></label>
     <label>Classification<select className="field" value={classification} onChange={e=>setClassification(e.target.value)}>{["public","internal","confidential","restricted"].map(x=><option key={x}>{x}</option>)}</select></label>
     <label className="wide">Content<textarea className="field" rows={4} value={content} onChange={e=>setContent(e.target.value)}/></label></div>
    <button className="button" disabled={busy||!key.trim()||!title.trim()||!content.trim()} onClick={()=>void addKnowledge()}>Create version</button>
    <div className="activity">{knowledge.map(x=><div className="activity-row" key={x.id}><span className="activity-dot"/><div><div className="activity-title">{x.title} · v{x.version}</div><div className="activity-meta">{x.key} · {x.classification} · {x.status}</div><p>{x.content}</p>{x.status==="draft"&&<button className="button secondary" disabled={busy} onClick={()=>void approve(x.id)}>Approve as founder</button>}</div></div>)}</div>
    {!knowledge.length&&<div className="empty">No governed knowledge has been recorded.</div>}
   </section>
   <section className="panel"><div className="panel-head"><div className="panel-title">Workflow drafts</div><span className="panel-note">{drafts.length} records</span></div>
    <div className="form-grid"><label>Workflow<select className="field" value={kind} onChange={e=>setKind(e.target.value)}><option value="front_desk">Front desk enquiry</option><option value="meeting_proposal">Meeting to proposal</option><option value="receivable_followup">Receivables follow-up</option></select></label>
     <label>Source record<select className="field" value={sourceId} onChange={e=>setSourceId(e.target.value)}><option value="">Choose a source record</option>{sourceOptions.map(option=><option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
     <label className="wide">Draft content (JSON)<textarea className="field" rows={5} value={draftContent} onChange={e=>setDraftContent(e.target.value)} placeholder='{"summary":"…","suggested_reply":"…","open_questions":["…"]}'/></label></div>
    <button className="button" disabled={busy||!sourceId.trim()} onClick={()=>void addDraft()}>Save source-linked draft</button>
    <div className="activity">{drafts.map(x=><div className="activity-row" key={x.id}><span className="activity-dot"/><div><div className="activity-title">{x.kind.replaceAll("_"," ")} · {x.status}</div><div className="activity-meta">Sources: {x.source_refs.map(s=>s.type+":"+s.id).join(", ")}</div><pre className="activity-meta" style={{whiteSpace:"pre-wrap"}}>{JSON.stringify(x.content,null,2)}</pre>{x.status==="draft"&&<div className="actions"><button className="button secondary" disabled={busy} onClick={()=>void review(x.id,"reviewed")}>Mark reviewed</button><button className="button secondary" disabled={busy} onClick={()=>void review(x.id,"rejected")}>Reject</button></div>}</div></div>)}</div>
    {!drafts.length&&<div className="empty">No workflow drafts have been saved.</div>}
   </section>
  </div>
 </Page>;
}
