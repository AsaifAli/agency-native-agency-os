"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Contact = { id: string; first_name: string; last_name: string; email: string };
type Lead = { id: string; company_name: string; stage: string; contact_id: string | null };
type Sender = { id: string; display_name: string; email_address: string; status: string; max_per_hour: number; max_per_day: number };
type Message = { id: string; sender_id: string; contact_id: string; lead_id: string | null; recipient: string; subject: string; body: string; status: string; approval_id: string | null; stop_reason: string; queued_at: string | null; sent_at: string | null; provider_message_id: string | null };
type Block = { id: string; contact_id: string; channel: string; status: string; reason: string; note: string; recorded_at: string };
function contactLabel(item: Contact) { return [item.first_name,item.last_name].filter(Boolean).join(" ") + " · " + item.email; }

export default function OutreachPage() {
  const [workspaces,setWorkspaces] = useState<Workspace[]>([]);
  const [workspace,setWorkspace] = useState("");
  const [contacts,setContacts] = useState<Contact[]>([]);
  const [leads,setLeads] = useState<Lead[]>([]);
  const [senders,setSenders] = useState<Sender[]>([]);
  const [messages,setMessages] = useState<Message[]>([]);
  const [blocks,setBlocks] = useState<Block[]>([]);
  const [senderName,setSenderName] = useState("Agency Team");
  const [senderEmail,setSenderEmail] = useState("");
  const [maxHour,setMaxHour] = useState("10");
  const [maxDay,setMaxDay] = useState("50");
  const [consentContact,setConsentContact] = useState("");
  const [consentStatus,setConsentStatus] = useState("granted");
  const [consentSource,setConsentSource] = useState("");
  const [consentEvidence,setConsentEvidence] = useState("");
  const [consentNote,setConsentNote] = useState("");
  const [senderId,setSenderId] = useState("");
  const [contactId,setContactId] = useState("");
  const [leadId,setLeadId] = useState("");
  const [subject,setSubject] = useState("");
  const [body,setBody] = useState("");
  const [purpose,setPurpose] = useState("");
  const [eventNotes,setEventNotes] = useState<Record<string,string>>({});
  const [releaseNotes,setReleaseNotes] = useState<Record<string,string>>({});
  const [error,setError] = useState("");
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState(false);
  const [busyId,setBusyId] = useState("");

  useEffect(() => {
    async function loadWorkspaces() {
      try {
        if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
        setWorkspaces(rows);
        if (rows[0]) setWorkspace(rows[0].id);
        else setLoading(false);
      } catch (e) {
        setError((e as Error).message); setLoading(false);
      }
    }
    void loadWorkspaces();
  }, []);

  const loadData = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true); setError("");
    try {
      const [contactRows,leadRows,senderRows,messageRows,blockRows] = await Promise.all([
        api<Contact[]>(`/v1/orgs/${orgId()}/contacts?workspace_id=${encodeURIComponent(workspace)}`),
        api<Lead[]>(`/v1/orgs/${orgId()}/leads?workspace_id=${encodeURIComponent(workspace)}`),
        api<Sender[]>(`/v1/orgs/${orgId()}/outreach/senders?workspace_id=${encodeURIComponent(workspace)}`),
        api<Message[]>(`/v1/orgs/${orgId()}/outreach/messages?workspace_id=${encodeURIComponent(workspace)}`),
        api<Block[]>(`/v1/orgs/${orgId()}/outreach/blocks?workspace_id=${encodeURIComponent(workspace)}&status=active`),
      ]);
      setContacts(contactRows.filter(item => !!item.email));
      setLeads(leadRows);
      setSenders(senderRows);
      setMessages(messageRows);
      setBlocks(blockRows);
      setSenderId(current => senderRows.some(item => item.id===current) ? current : senderRows.find(item => item.status==="active")?.id || senderRows[0]?.id || "");
      setContactId(current => contactRows.some(item => item.id===current && !!item.email) ? current : contactRows.find(item => !!item.email)?.id || "");
      setConsentContact(current => contactRows.some(item => item.id===current && !!item.email) ? current : contactRows.find(item => !!item.email)?.id || "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  },[workspace]);

  useEffect(() => { void loadData(); },[loadData]);

  async function createSender(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      await api<Sender>(`/v1/orgs/${orgId()}/outreach/senders`,{
        method:"POST",body:JSON.stringify({
          workspace_id:workspace,display_name:senderName.trim(),email_address:senderEmail.trim(),
          max_per_hour:Number(maxHour),max_per_day:Number(maxDay),
        }),
      });
      setSenderEmail(""); await loadData();
    } catch(e) { setError((e as Error).message); } finally { setSaving(false); }
  }

  async function senderStatus(item: Sender,status:"active"|"paused") {
    setBusyId(item.id); setError("");
    try {
      await api<Sender>(`/v1/orgs/${orgId()}/outreach/senders/${item.id}/status`,{
        method:"PATCH",body:JSON.stringify({status}),
      });
      await loadData();
    } catch(e) { setError((e as Error).message); } finally { setBusyId(""); }
  }

  async function recordConsent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    const basis = consentStatus==="legitimate_interest_reviewed" ? "legitimate_interest" : "consent";
    try {
      await api(`/v1/orgs/${orgId()}/outreach/consents`,{
        method:"POST",body:JSON.stringify({
          workspace_id:workspace,contact_id:consentContact,channel:"email",status:consentStatus,
          legal_basis:basis,source:consentSource.trim(),evidence_reference:consentEvidence.trim(),
          review_note:consentNote.trim(),
        }),
      });
      setConsentSource(""); setConsentEvidence(""); setConsentNote("");
      await loadData();
    } catch(e) { setError((e as Error).message); } finally { setSaving(false); }
  }

  async function createMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      await api<Message>(`/v1/orgs/${orgId()}/outreach/messages`,{
        method:"POST",body:JSON.stringify({
          workspace_id:workspace,sender_id:senderId,contact_id:contactId,lead_id:leadId||null,
          subject:subject.trim(),body:body.trim(),purpose:purpose.trim(),
        }),
      });
      setSubject(""); setBody(""); setPurpose(""); await loadData();
    } catch(e) { setError((e as Error).message); } finally { setSaving(false); }
  }

  async function messageAction(item:Message,action:"submit-for-approval"|"queue") {
    setBusyId(item.id); setError("");
    try {
      await api<Message>(`/v1/orgs/${orgId()}/outreach/messages/${item.id}/${action}`,{method:"POST"});
      await loadData();
    } catch(e) { setError((e as Error).message); } finally { setBusyId(""); }
  }

  async function rejectMessage(item:Message) {
    if (!item.approval_id) return;
    setBusyId(item.id); setError("");
    try {
      await api<Message>(`/v1/orgs/${orgId()}/outreach/messages/${item.id}/reject`,{
        method:"POST",body:JSON.stringify({approval_id:item.approval_id,note:"Founder rejected this outreach draft"}),
      });
      await loadData();
    } catch(e) { setError((e as Error).message); } finally { setBusyId(""); }
  }

  async function stopEvent(item:Message,eventType:"reply"|"opt_out"|"bounce") {
    setBusyId(item.id); setError("");
    try {
      await api(`/v1/orgs/${orgId()}/outreach/messages/${item.id}/events`,{
        method:"POST",body:JSON.stringify({
          event_type:eventType,source:"manual",note:(eventNotes[item.id]||"").trim(),
        }),
      });
      await loadData();
    } catch(e) { setError((e as Error).message); } finally { setBusyId(""); }
  }

  async function releaseBlock(item:Block) {
    const note=(releaseNotes[item.id]||"").trim();
    if(note.length<3){setError("A founder release note is required.");return;}
    setBusyId(item.id);setError("");
    try{
      await api(`/v1/orgs/${orgId()}/outreach/blocks/${item.id}/release`,{
        method:"POST",body:JSON.stringify({note}),
      });
      await loadData();
    }catch(e){setError((e as Error).message);}finally{setBusyId("");}
  }

  return (
    <Page eyebrow="REVENUE ENGINE" title="Outreach control" description="Manage approved sender identities, channel-specific consent evidence, reviewed email drafts, approval and rate limits, plus stop-on-reply, opt-out and bounce safeguards.">
      <Notice>This prepares an internal, founder-approved email queue only. It does not send messages or store provider credentials. Sender activation and consent evidence require Founder Authority. Provider dispatch and signed webhooks are intentionally deferred until external integrations and compliance review.</Notice>
      <section className="panel">
        <div className="panel-head"><div className="panel-title">Workspace</div><select className="field" value={workspace} onChange={e=>setWorkspace(e.target.value)}>{workspaces.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Approved sender identities</h2>
        <form onSubmit={createSender} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(170px,1fr))",gap:8,marginBottom:14}}>
          <input className="field" value={senderName} onChange={e=>setSenderName(e.target.value)} placeholder="Display name" maxLength={160} required/>
          <input className="field" type="email" value={senderEmail} onChange={e=>setSenderEmail(e.target.value)} placeholder="Sender email address" maxLength={320} required/>
          <input className="field" type="number" value={maxHour} onChange={e=>setMaxHour(e.target.value)} placeholder="Max per hour" min={1} max={100}/>
          <input className="field" type="number" value={maxDay} onChange={e=>setMaxDay(e.target.value)} placeholder="Max per day" min={1} max={1000}/>
          <button className="button primary" type="submit" disabled={saving}>{saving?"Saving…":"Create sender draft"}</button>
        </form>
        {loading ? <div className="empty">Loading outreach controls…</div> : <div className="activity">
          {senders.map(item=><div className="activity-row" key={item.id}><span className="activity-dot"/><div style={{width:"100%"}}>
            <div className="activity-title">{item.display_name} · {item.email_address}</div>
            <div className="activity-meta">{item.status} · {item.max_per_hour}/hour · {item.max_per_day}/day</div>
            {item.status!=="active" && <button className="button secondary" type="button" onClick={()=>void senderStatus(item,"active")} disabled={busyId===item.id}>Activate (Founder Authority)</button>}
            {item.status==="active" && <button className="button secondary" type="button" onClick={()=>void senderStatus(item,"paused")} disabled={busyId===item.id}>Pause sender</button>}
          </div></div>)}
          {!senders.length && <div className="empty">No sender identities yet. Create a draft, then activate it with Founder Authority.</div>}
        </div>}
      </section>

      <section className="panel">
        <h2 className="panel-title">Record channel consent evidence</h2>
        <form onSubmit={recordConsent} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:8}}>
          <select className="field" value={consentContact} onChange={e=>setConsentContact(e.target.value)} required>{contacts.map(item=><option key={item.id} value={item.id}>{contactLabel(item)}</option>)}</select>
          <select className="field" value={consentStatus} onChange={e=>setConsentStatus(e.target.value)}>
            <option value="granted">Explicit consent granted</option><option value="legitimate_interest_reviewed">Legitimate interest reviewed</option><option value="withdrawn">Withdrawn</option><option value="unknown">Unknown</option>
          </select>
          <input className="field" value={consentSource} onChange={e=>setConsentSource(e.target.value)} placeholder="Source (form, email, referral…)" maxLength={160} required/>
          <input className="field" value={consentEvidence} onChange={e=>setConsentEvidence(e.target.value)} placeholder="Evidence reference" maxLength={240} required/>
          <input className="field" value={consentNote} onChange={e=>setConsentNote(e.target.value)} placeholder="Founder review note (required for LI)" maxLength={2000}/>
          <button className="button primary" type="submit" disabled={saving||!consentContact}>{saving?"Recording…":"Record consent evidence"}</button>
        </form>
        <div className="activity-meta" style={{marginTop:8}}>Consent records are append-only. A new record never silently clears an existing stop block; release is a separate founder action.</div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Prepare outbound email draft</h2>
        <form onSubmit={createMessage} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:8}}>
          <select className="field" value={senderId} onChange={e=>setSenderId(e.target.value)} required><option value="">Select sender</option>{senders.map(item=><option key={item.id} value={item.id}>{item.display_name} · {item.status}</option>)}</select>
          <select className="field" value={contactId} onChange={e=>setContactId(e.target.value)} required><option value="">Select contact</option>{contacts.map(item=><option key={item.id} value={item.id}>{contactLabel(item)}</option>)}</select>
          <select className="field" value={leadId} onChange={e=>setLeadId(e.target.value)}><option value="">No linked lead</option>{leads.map(item=><option key={item.id} value={item.id}>{item.company_name} · {item.stage}</option>)}</select>
          <input className="field" value={subject} onChange={e=>setSubject(e.target.value)} placeholder="Email subject" maxLength={240} minLength={2} required/>
          <input className="field" value={purpose} onChange={e=>setPurpose(e.target.value)} placeholder="Business purpose" maxLength={240}/>
          <textarea className="field" value={body} onChange={e=>setBody(e.target.value)} placeholder="Reviewed email body" maxLength={20000} minLength={10} rows={5} style={{gridColumn:"1 / -1"}} required/>
          <button className="button primary" type="submit" disabled={saving||!senderId||!contactId}>{saving?"Saving…":"Save email draft"}</button>
        </form>
      </section>

      <section className="panel">
        <div className="panel-head"><div className="panel-title">Outbound message register <span className="activity-meta">({messages.length})</span></div><button className="button secondary" type="button" onClick={()=>void loadData()}>Refresh</button></div>
        {messages.map(item=><div className="activity-row" key={item.id} style={{alignItems:"flex-start"}}><span className="activity-dot"/><div style={{width:"100%"}}>
          <div className="activity-title">{item.subject}</div>
          <div className="activity-meta">To {item.recipient} · {item.status} · {item.stop_reason||"No stop condition"}</div>
          <p className="activity-meta" style={{whiteSpace:"pre-wrap"}}>{item.body}</p>
          {(item.status==="draft" || item.status==="rejected") && <button className="button secondary" type="button" onClick={()=>void messageAction(item,"submit-for-approval")} disabled={busyId===item.id}>Submit for Founder Approval</button>}
          {item.status==="pending_approval" && <div style={{display:"flex",gap:8,flexWrap:"wrap"}}><Link href="/approvals" className="activity-meta">Review in Founder Approvals</Link><button className="button primary" type="button" onClick={()=>void messageAction(item,"queue")} disabled={busyId===item.id}>Queue after approval</button><button className="button secondary" type="button" onClick={()=>void rejectMessage(item)} disabled={busyId===item.id}>Reject draft</button></div>}
          {item.status==="queued" && <div style={{display:"grid",gridTemplateColumns:"minmax(180px,1fr) repeat(3,auto)",gap:8,marginTop:8}}>
            <input className="field" value={eventNotes[item.id]||""} onChange={e=>setEventNotes(v=>({...v,[item.id]:e.target.value}))} placeholder="Manual reply / opt-out / bounce evidence" maxLength={2000}/>
            <button className="button secondary" type="button" onClick={()=>void stopEvent(item,"reply")} disabled={busyId===item.id}>Record reply</button>
            <button className="button secondary" type="button" onClick={()=>void stopEvent(item,"opt_out")} disabled={busyId===item.id}>Record opt-out</button>
            <button className="button secondary" type="button" onClick={()=>void stopEvent(item,"bounce")} disabled={busyId===item.id}>Record bounce</button>
          </div>}
          {item.status==="queued" && <div className="activity-meta">Queued internally only; no provider send has occurred.</div>}
          {item.approval_id && <div className="activity-meta">Approval {item.approval_id}</div>}
        </div></div>)}
        {!messages.length && <div className="empty">No outbound drafts yet.</div>}
      </section>

      <section className="panel">
        <h2 className="panel-title">Active communication blocks</h2>
        {blocks.map(item=><div className="activity-row" key={item.id}><span className="activity-dot"/><div style={{width:"100%"}}>
          <div className="activity-title">{contacts.find(contact=>contact.id===item.contact_id)?.email || item.contact_id} · {item.reason}</div>
          <div className="activity-meta">{item.channel} · {item.status} · {item.note}</div>
          <div style={{display:"grid",gridTemplateColumns:"minmax(180px,1fr) auto",gap:8,marginTop:8}}>
            <input className="field" value={releaseNotes[item.id]||""} onChange={e=>setReleaseNotes(v=>({...v,[item.id]:e.target.value}))} placeholder="Founder release rationale" maxLength={2000}/>
            <button className="button secondary" type="button" onClick={()=>void releaseBlock(item)} disabled={busyId===item.id}>Release (Founder Authority)</button>
          </div>
        </div></div>)}
        {!blocks.length && <div className="empty">No active email stop blocks.</div>}
      </section>
    </Page>
  );
}
