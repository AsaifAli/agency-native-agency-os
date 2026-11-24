"use client";

import { useEffect, useState } from "react";
import Page from "@/components/page";
import { api, orgId, Workspace, Execution, AuditEvent } from "@/lib/api";

const statusClass = (status: string) => ["succeeded", "failed", "cancelled"].includes(status) ? status : "pending";

export default function Workflows() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selected, setSelected] = useState<Execution | null>(null);
  const [trace, setTrace] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(workspaceId = workspace) {
    setError("");
    setLoading(true);
    try {
      const rows = await api<Execution[]>(`/v1/orgs/${orgId()}/executions?workspace_id=${encodeURIComponent(workspaceId)}&limit=200`);
      setExecutions(rows);
      if (selected && !rows.some((row) => row.id === selected.id)) {
        setSelected(null);
        setTrace([]);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function showTrace(item: Execution) {
    setSelected(item);
    setTrace([]);
    setError("");
    try {
      const rows = await api<AuditEvent[]>(`/v1/orgs/${orgId()}/executions/${item.id}/trace?workspace_id=${encodeURIComponent(item.workspace_id)}`);
      setTrace(rows);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    if (!orgId()) { setError("Set NEXT_PUBLIC_ORG_ID first."); return; }
    api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`)
      .then((rows) => {
        setWorkspaces(rows);
        if (rows[0]) {
          setWorkspace(rows[0].id);
          return load(rows[0].id);
        }
      })
      .catch((e) => setError(e.message));
  }, []);

  return (
    <Page eyebrow="AUTOMATION" title="Processes" description="Inspect durable Agency OS executions, attempts and lifecycle events. Business state and authorization remain owned by the OS.">
      <div className="notice">Read-only operational view. Workers execute only registered runtime capabilities; no external side-effect handlers are enabled by default.</div>
      <section className="panel">
        <div className="panel-head"><div className="panel-title">Execution history</div><span className="panel-note">{executions.length} records</span></div>
        <div className="form-grid">
          <label>Workspace<select className="field" value={workspace} onChange={(e) => { setWorkspace(e.target.value); setSelected(null); setTrace([]); load(e.target.value); }}>{workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
          <div style={{display:"flex",alignItems:"end"}}><button className="button secondary" onClick={() => load()} disabled={!workspace || loading}>{loading ? "Refreshing…" : "Refresh"}</button></div>
        </div>
        {error && <div className="error">{error}</div>}
        <div className="table-wrap"><table className="data-table"><thead><tr><th>Execution</th><th>Runtime</th><th>Status</th><th>Attempts</th><th>Queued</th><th>Details</th></tr></thead>
          <tbody>{executions.map((item) => <tr key={item.id}><td><code>{item.id.slice(0, 12)}</code><div className="activity-meta">Task {item.task_id.slice(0, 10)}</div></td><td>{item.runtime}</td><td><span className={`status ${statusClass(item.status)}`}>{item.status}</span></td><td>{item.attempt_count}/{item.max_attempts}</td><td>{new Date(item.queued_at).toLocaleString()}</td><td><button className="button secondary" onClick={() => showTrace(item)}>View trace</button></td></tr>)}</tbody>
        </table></div>
        {!executions.length && !loading && <div className="empty">No execution records in this workspace yet. Queue a task through an enabled runtime to see its lifecycle here.</div>}
      </section>
      {selected && <section className="panel" style={{marginTop:16}}>
        <div className="panel-head"><div className="panel-title">Execution trace · {selected.id.slice(0, 12)}</div><span className={`status ${statusClass(selected.status)}`}>{selected.status}</span></div>
        <div className="activity">
          {trace.map((event) => <div className="activity-row" key={event.id}><span className="activity-dot"/><div><div className="activity-title">{event.event_type}</div><div className="activity-meta">{event.resource_type} · {new Date(event.created_at).toLocaleString()}</div>{Object.keys(event.payload || {}).length > 0 && <pre style={{whiteSpace:"pre-wrap",fontSize:12,marginTop:6}}>{JSON.stringify(event.payload, null, 2)}</pre>}</div></div>)}
        </div>
        {!trace.length && <div className="empty">No lifecycle events are available for this execution.</div>}
        {selected.error_code && <div className="error">{selected.error_code}: {selected.error_message || "No additional error detail."}</div>}
      </section>}
    </Page>
  );
}
