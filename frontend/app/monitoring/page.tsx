"use client";

import { useEffect, useState } from "react";
import Page from "@/components/page";
import Stat from "@/components/stat";
import { api, orgId, Workspace, Execution } from "@/lib/api";

export default function Monitoring() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [items, setItems] = useState<Execution[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(workspaceId = workspace) {
    if (!workspaceId) return;
    setLoading(true);
    setError("");
    try {
      setItems(await api<Execution[]>(`/v1/orgs/${orgId()}/executions?workspace_id=${encodeURIComponent(workspaceId)}&limit=500`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!orgId()) { setError("Set NEXT_PUBLIC_ORG_ID first."); return; }
    api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`).then((rows) => {
      setWorkspaces(rows);
      if (rows[0]) { setWorkspace(rows[0].id); return load(rows[0].id); }
    }).catch((e) => setError(e.message));
  }, []);

  const active = items.filter((x) => ["queued", "claimed", "running", "retry_wait"].includes(x.status)).length;
  const failed = items.filter((x) => x.status === "failed").length;
  const succeeded = items.filter((x) => x.status === "succeeded").length;
  const retries = items.reduce((sum, x) => sum + Math.max(0, x.attempt_count - 1), 0);

  return <Page eyebrow="OPERATIONS" title="Monitoring" description="Operational visibility from persisted execution records. This view does not imply provider health or production readiness.">
    <div className="notice">Current metrics are derived from Agency OS execution records only. Provider latency, token cost, infrastructure metrics, logs, alert delivery and distributed tracing are not yet integrated.</div>
    <div className="panel"><div className="form-grid">
      <label>Workspace<select className="field" value={workspace} onChange={(e) => { setWorkspace(e.target.value); load(e.target.value); }}>{workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <div style={{display:"flex",alignItems:"end"}}><button className="button secondary" onClick={() => load()} disabled={!workspace || loading}>{loading ? "Refreshing…" : "Refresh metrics"}</button></div>
    </div>{error && <div className="error">{error}</div>}</div>
    <div style={{height:16}}/>
    <div className="grid stats">
      <Stat label="Executions" value={items.length} foot="Persisted in selected workspace" icon="↗"/>
      <Stat label="Active / waiting" value={active} foot="Queued, claimed, running or retry wait" icon="◷"/>
      <Stat label="Succeeded" value={succeeded} foot="Persisted successful outcomes" icon="✓"/>
      <Stat label="Failed" value={failed} foot="Terminal failures" icon="!"/>
    </div>
    <div style={{height:16}}/>
    <section className="panel"><div className="panel-head"><div className="panel-title">Recent execution health</div><span className="panel-note">{retries} retry attempts beyond first attempt</span></div>
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Execution</th><th>Status</th><th>Attempts</th><th>Error</th><th>Updated</th></tr></thead><tbody>
        {items.slice(0,30).map((x) => <tr key={x.id}><td><code>{x.id.slice(0,12)}</code></td><td><span className={`status ${["succeeded","failed","cancelled"].includes(x.status) ? x.status : "pending"}`}>{x.status}</span></td><td>{x.attempt_count}/{x.max_attempts}</td><td>{x.error_code || "—"}</td><td>{new Date(x.updated_at).toLocaleString()}</td></tr>)}
      </tbody></table></div>
      {!items.length && !loading && <div className="empty">No execution telemetry is available for this workspace yet.</div>}
    </section>
  </Page>;
}
