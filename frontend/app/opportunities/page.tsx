"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Lead = { id: string; company_name: string; stage: string };
type Client = { id: string; name: string };
type Opportunity = {
  id: string;
  workspace_id: string;
  client_id: string | null;
  lead_id: string | null;
  title: string;
  stage: string;
  amount_minor: number;
  currency: string;
  probability: number;
  expected_close_date: string | null;
  created_at: string;
};
const stages = ["qualification", "discovery", "proposal", "negotiation", "won", "lost"];

function money(amountMinor: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amountMinor / 100);
}

export default function OpportunitiesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [probability, setProbability] = useState("20");
  const [leadId, setLeadId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientDrafts, setClientDrafts] = useState<Record<string,string>>({});
  const [stageDrafts, setStageDrafts] = useState<Record<string,string>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingId, setSavingId] = useState("");

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
      const [opps, leadRows, clientRows] = await Promise.all([
        api<Opportunity[]>(`/v1/orgs/${orgId()}/opportunities?workspace_id=${encodeURIComponent(workspace)}`),
        api<Lead[]>(`/v1/orgs/${orgId()}/leads?workspace_id=${encodeURIComponent(workspace)}`),
        api<Client[]>(`/v1/orgs/${orgId()}/clients?workspace_id=${encodeURIComponent(workspace)}`),
      ]);
      setOpportunities(opps);
      setLeads(leadRows.filter(row => row.stage !== "suppressed" && row.stage !== "unqualified"));
      setClients(clientRows);
      setStageDrafts(Object.fromEntries(opps.map(row => [row.id, row.stage])));
      setClientDrafts(Object.fromEntries(opps.map(row => [row.id, row.client_id || ""])));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function createOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const numericAmount = Number(amount);
    if (!workspace || title.trim().length < 2 || !Number.isFinite(numericAmount) || numericAmount < 0) return;
    setSaving(true);
    setError("");
    try {
      await api<Opportunity>(`/v1/orgs/${orgId()}/opportunities`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          title: title.trim(),
          amount_minor: Math.round(numericAmount * 100),
          currency: "INR",
          probability: Math.max(0, Math.min(100, Number(probability) || 0)),
          lead_id: leadId || null,
          client_id: clientId || null,
        }),
      });
      setTitle(""); setAmount(""); setProbability("20"); setLeadId(""); setClientId("");
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function updateStage(item: Opportunity) {
    const stage = stageDrafts[item.id] || item.stage;
    setSavingId(item.id);
    setError("");
    try {
      await api<Opportunity>(`/v1/orgs/${orgId()}/opportunities/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ stage, client_id: clientDrafts[item.id] || null }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSavingId("");
    }
  }

  return (
    <Page eyebrow="REVENUE ENGINE" title="Opportunities & sales pipeline" description="Track qualified commercial opportunities, indicative values, probability and stage progression. Commercial commitments remain subject to founder approval.">
      <Notice>Opportunity values are internal estimates, not approved quotations or contractual commitments. Moving an opportunity to won does not sign a contract, create an invoice or activate delivery.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Create opportunity</h2>
        <form onSubmit={createOpportunity} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10,marginBottom:22}}>
          <input className="field" value={title} onChange={e => setTitle(e.target.value)} placeholder="Opportunity / engagement title" maxLength={240} minLength={2} required />
          <input className="field" type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="Estimated value (INR)" min={0} step="0.01" required />
          <input className="field" type="number" value={probability} onChange={e => setProbability(e.target.value)} placeholder="Win probability %" min={0} max={100} />
          <select className="field" value={leadId} onChange={e => setLeadId(e.target.value)}>
            <option value="">No linked lead</option>
            {leads.map(lead => <option key={lead.id} value={lead.id}>{lead.company_name} · {lead.stage}</option>)}
          </select>
          <select className="field" value={clientId} onChange={e => setClientId(e.target.value)}>
            <option value="">No client linked yet</option>
            {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
          </select>
          <button className="button primary" type="submit" disabled={saving || !workspace}>{saving ? "Saving…" : "Create opportunity"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Sales opportunities <span className="activity-meta">({opportunities.length})</span></div>
          <button className="button secondary" type="button" onClick={() => void loadData()}>Refresh</button>
        </div>
        {loading ? <div className="empty">Loading opportunities…</div> : opportunities.length ? (
          <div className="activity">
            {opportunities.map(item => (
              <div className="activity-row" key={item.id} style={{alignItems:"flex-start"}}>
                <span className="activity-dot" />
                <div style={{minWidth:0,width:"100%"}}>
                  <div className="activity-title">{item.title}</div>
                  <div className="activity-meta">{money(item.amount_minor,item.currency)} · {item.probability}% probability · Created {new Date(item.created_at).toLocaleDateString()}</div>
                  <div className="activity-meta">Client: {clients.find(client => client.id === item.client_id)?.name || "Not linked"} · Lead: {leads.find(lead => lead.id === item.lead_id)?.company_name || "Not linked"}</div>
                  <div style={{display:"grid",gridTemplateColumns:"minmax(160px,220px) minmax(180px,1fr) auto",gap:8,marginTop:10}}>
                    <select className="field" value={stageDrafts[item.id] || item.stage} onChange={e => setStageDrafts(current => ({...current,[item.id]:e.target.value}))}>
                      {stages.map(stage => <option key={stage} value={stage}>{stage.replace("_"," ")}</option>)}
                    </select>
                    <select className="field" value={clientDrafts[item.id] ?? item.client_id ?? ""} onChange={e => setClientDrafts(current => ({...current,[item.id]:e.target.value}))}>
                      <option value="">No client linked</option>
                      {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
                    </select>
                    <button className="button secondary" type="button" onClick={() => void updateStage(item)} disabled={savingId===item.id}>{savingId===item.id ? "Saving…" : "Save changes"}</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : <div className="empty"><strong>No opportunities yet</strong>Create an opportunity when a prospect reaches a meaningful qualification or discovery stage.</div>}
      </section>
    </Page>
  );
}
