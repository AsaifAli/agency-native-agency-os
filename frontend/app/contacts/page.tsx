"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Contact = {
  id: string;
  workspace_id: string;
  client_id: string | null;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  job_title: string;
  source: string;
  consent_status: string;
  phone_call_consent_status: string;
  created_at: string;
};

type Activity = {
  id: string;
  workspace_id: string;
  contact_id: string;
  activity_type: string;
  direction: string;
  subject: string;
  body: string;
  outcome: string;
  source_reference: string;
  occurred_at: string;
  created_at: string;
};

export default function ContactsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedContact, setSelectedContact] = useState("");
  const [activities, setActivities] = useState<Activity[]>([]);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [source, setSource] = useState("");
  const [activityType, setActivityType] = useState("note");
  const [direction, setDirection] = useState("internal");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(false);
  const [savingContact, setSavingContact] = useState(false);
  const [savingActivity, setSavingActivity] = useState(false);

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

  const loadContacts = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true);
    setError("");
    try {
      const rows = await api<Contact[]>(
        `/v1/orgs/${orgId()}/contacts?workspace_id=${encodeURIComponent(workspace)}`
      );
      setContacts(rows);
      setSelectedContact(current => rows.some(row => row.id === current) ? current : rows[0]?.id || "");
    } catch (e) {
      setError((e as Error).message);
      setContacts([]);
      setSelectedContact("");
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadContacts(); }, [loadContacts]);

  const loadActivities = useCallback(async () => {
    if (!workspace || !selectedContact || !orgId()) {
      setActivities([]);
      return;
    }
    setActivityLoading(true);
    try {
      const rows = await api<Activity[]>(
        `/v1/orgs/${orgId()}/contacts/${selectedContact}/activities?workspace_id=${encodeURIComponent(workspace)}`
      );
      setActivities(rows);
    } catch (e) {
      setError((e as Error).message);
      setActivities([]);
    } finally {
      setActivityLoading(false);
    }
  }, [workspace, selectedContact]);

  useEffect(() => { void loadActivities(); }, [loadActivities]);

  async function createContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || firstName.trim().length < 1) return;
    setSavingContact(true);
    setError("");
    try {
      const created = await api<Contact>(`/v1/orgs/${orgId()}/contacts`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          phone: phone.trim(),
          job_title: jobTitle.trim(),
          source: source.trim(),
        }),
      });
      setFirstName(""); setLastName(""); setEmail(""); setPhone(""); setJobTitle(""); setSource("");
      await loadContacts();
      setSelectedContact(created.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSavingContact(false);
    }
  }

  async function createActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !selectedContact || !subject.trim()) return;
    setSavingActivity(true);
    setError("");
    try {
      await api<Activity>(`/v1/orgs/${orgId()}/contact-activities`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          contact_id: selectedContact,
          activity_type: activityType,
          direction,
          subject: subject.trim(),
          body: body.trim(),
          outcome: outcome.trim(),
        }),
      });
      setSubject(""); setBody(""); setOutcome("");
      await loadActivities();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSavingActivity(false);
    }
  }

  const selected = contacts.find(contact => contact.id === selectedContact);

  return (
    <Page eyebrow="REVENUE ENGINE" title="Contacts & relationship history" description="Keep a workspace-scoped record of people, conversations, meetings and follow-ups. Historical activity is recorded here; this screen does not send messages or place calls.">
      <Notice>Contact consent is channel-specific. Recording a note or email history does not authorize outreach, and this page never sends communications. Phone-call consent is managed separately under Founder Authority.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={event => setWorkspace(event.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Add contact</h2>
        <form onSubmit={createContact} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10,marginBottom:24}}>
          <input className="field" value={firstName} onChange={e => setFirstName(e.target.value)} placeholder="First name" maxLength={120} required />
          <input className="field" value={lastName} onChange={e => setLastName(e.target.value)} placeholder="Last name" maxLength={120} />
          <input className="field" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" maxLength={320} />
          <input className="field" value={phone} onChange={e => setPhone(e.target.value)} placeholder="Phone" maxLength={50} />
          <input className="field" value={jobTitle} onChange={e => setJobTitle(e.target.value)} placeholder="Job title" maxLength={160} />
          <input className="field" value={source} onChange={e => setSource(e.target.value)} placeholder="Source / referral" maxLength={120} />
          <button className="button primary" type="submit" disabled={savingContact || !workspace}>{savingContact ? "Saving…" : "Add contact"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Relationship history</div>
          <button className="button secondary" type="button" onClick={() => void loadContacts()}>Refresh contacts</button>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"minmax(220px,0.8fr) minmax(0,1.6fr)",gap:18}}>
          <div className="activity">
            {loading ? <div className="empty">Loading contacts…</div> : contacts.length ? contacts.map(contact => (
              <button key={contact.id} type="button" onClick={() => setSelectedContact(contact.id)} className="activity-row" style={{width:"100%",textAlign:"left",background:selectedContact===contact.id?"var(--panel-strong, rgba(127,127,127,.12))":"transparent",border:0,cursor:"pointer",color:"inherit"}}>
                <span className="activity-dot" />
                <span style={{minWidth:0}}>
                  <span className="activity-title" style={{display:"block"}}>{contact.first_name} {contact.last_name}</span>
                  <span className="activity-meta">{contact.email || contact.phone || "No contact channel recorded"}</span>
                </span>
              </button>
            )) : <div className="empty">No contacts in this workspace yet.</div>}
          </div>
          <div style={{minWidth:0}}>
            {selected ? <>
              <div className="panel-head">
                <div>
                  <div className="panel-title">{selected.first_name} {selected.last_name}</div>
                  <div className="activity-meta">{selected.job_title || "Role not recorded"} · {selected.email || "No email"} · {selected.phone || "No phone"}</div>
                  <div className="activity-meta">Email/contact consent: {selected.consent_status} · Phone-call consent: {selected.phone_call_consent_status}</div>
                </div>
                <button className="button secondary" type="button" onClick={() => void loadActivities()}>Refresh history</button>
              </div>
              <form onSubmit={createActivity} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:10,marginBottom:18}}>
                <select className="field" value={activityType} onChange={e => setActivityType(e.target.value)}>
                  <option value="note">Note</option><option value="call">Call history</option><option value="email">Email history</option><option value="meeting">Meeting</option><option value="task">Follow-up task</option><option value="status_update">Status update</option>
                </select>
                <select className="field" value={direction} onChange={e => setDirection(e.target.value)}>
                  <option value="internal">Internal</option><option value="inbound">Inbound</option><option value="outbound">Outbound</option><option value="none">Not applicable</option>
                </select>
                <input className="field" value={subject} onChange={e => setSubject(e.target.value)} placeholder="Activity subject" maxLength={240} required />
                <input className="field" value={outcome} onChange={e => setOutcome(e.target.value)} placeholder="Outcome / next step" maxLength={240} />
                <textarea className="field" value={body} onChange={e => setBody(e.target.value)} placeholder="Short factual summary (do not paste secrets or full call transcripts)" maxLength={4000} rows={3} style={{gridColumn:"1 / -1"}} />
                <button className="button primary" type="submit" disabled={savingActivity || !selectedContact}>{savingActivity ? "Saving…" : "Record activity"}</button>
              </form>
              <div className="activity">
                {activityLoading ? <div className="empty">Loading relationship history…</div> : activities.length ? activities.map(item => (
                  <div className="activity-row" key={item.id}>
                    <span className="activity-dot" />
                    <div style={{minWidth:0}}>
                      <div className="activity-title">{item.subject}</div>
                      <div className="activity-meta">{item.activity_type.replace("_"," ")} · {item.direction} · {new Date(item.occurred_at).toLocaleString()}</div>
                      {item.body && <p className="activity-meta" style={{whiteSpace:"pre-wrap"}}>{item.body}</p>}
                      {item.outcome && <div className="activity-meta">Outcome: {item.outcome}</div>}
                    </div>
                  </div>
                )) : <div className="empty">No activity recorded for this contact yet.</div>}
              </div>
            </> : <div className="empty">Select a contact to view or record relationship history.</div>}
          </div>
        </div>
      </section>
    </Page>
  );
}
