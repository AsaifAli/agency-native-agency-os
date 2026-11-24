"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type ClientRecord = {
  id: string;
  workspace_id: string;
  name: string;
  legal_name: string | null;
  industry: string;
  website: string;
  status: string;
  created_at: string;
};

export default function ClientsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [clients, setClients] = useState<ClientRecord[]>([]);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [website, setWebsite] = useState("");
  const [legalName, setLegalName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

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

  const loadClients = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true);
    setError("");
    try {
      const rows = await api<ClientRecord[]>(
        `/v1/orgs/${orgId()}/clients?workspace_id=${encodeURIComponent(workspace)}`
      );
      setClients(rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadClients(); }, [loadClients]);

  async function createClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || name.trim().length < 2) return;
    setSaving(true);
    setError("");
    try {
      await api<ClientRecord>(`/v1/orgs/${orgId()}/clients`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          name: name.trim(),
          legal_name: legalName.trim() || null,
          industry: industry.trim(),
          website: website.trim(),
        }),
      });
      setName("");
      setLegalName("");
      setIndustry("");
      setWebsite("");
      await loadClients();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Page eyebrow="REVENUE & DELIVERY" title="Client registry" description="Manage client organizations inside the selected workspace. Client data remains scoped to its workspace.">
      <Notice>Creating a client record does not provision external accounts, send communications, sign agreements, or activate delivery. Those actions remain separate governed workflows.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={event => setWorkspace(event.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        {!workspaces.length && !loading ? <div className="empty"><strong>No workspace available</strong>Create or initialize a workspace before adding client records.</div> : (
          <>
            <form onSubmit={createClient} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10,marginBottom:18}}>
              <input className="field" value={name} onChange={event => setName(event.target.value)} placeholder="Client / company name" minLength={2} maxLength={200} required />
              <input className="field" value={legalName} onChange={event => setLegalName(event.target.value)} placeholder="Legal name (optional)" maxLength={240} />
              <input className="field" value={industry} onChange={event => setIndustry(event.target.value)} placeholder="Industry" maxLength={120} />
              <input className="field" value={website} onChange={event => setWebsite(event.target.value)} placeholder="Website URL" maxLength={500} />
              <button className="button primary" type="submit" disabled={saving || !workspace}>{saving ? "Saving…" : "Add client"}</button>
            </form>
            <div className="panel-head"><div className="panel-title">Client organizations</div><button className="button secondary" type="button" onClick={() => void loadClients()}>Refresh</button></div>
            {loading ? <div className="empty">Loading client records…</div> : clients.length ? (
              <div className="activity">
                {clients.map(item => (
                  <div className="activity-row" key={item.id}>
                    <span className="activity-dot" />
                    <div style={{minWidth:0}}>
                      <div className="activity-title">{item.name}</div>
                      <div className="activity-meta">{item.legal_name || "Legal name not recorded"} · {item.industry || "Industry not set"} · {item.status}</div>
                      {item.website && <a href={item.website} target="_blank" rel="noreferrer" className="activity-meta">{item.website}</a>}
                      <div className="activity-meta">Created {new Date(item.created_at).toLocaleDateString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : <div className="empty"><strong>No clients in this workspace yet</strong>Add a client organization above when a prospect becomes a client. Prospect research and lead qualification remain in the Revenue workflow.</div>}
          </>
        )}
      </section>
    </Page>
  );
}
