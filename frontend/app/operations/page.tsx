"use client";

import { useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type ExceptionItem = {
  kind: string; id: string; title: string; status: string;
  resource_id: string; created_at: string | null;
  action_type?: string; error_code?: string | null;
  error_message?: string | null; attempt_count?: number; max_attempts?: number;
};
type AgentMetric = {
  agent_id: string; name: string; department: string;
  executions: number; succeeded: number; failed: number; active: number; attempts: number;
};

export default function OperationsPage() {
  const [workspace, setWorkspace] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [agents, setAgents] = useState<AgentMetric[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState("");

  useEffect(() => {
    async function load() {
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
    load();
  }, []);

  useEffect(() => {
    async function loadWorkspace() {
      if (!workspace) return;
      setLoading(true);
      setError("");
      try {
        const [inbox, performance] = await Promise.all([
          api<{items: ExceptionItem[]}>(`/v1/orgs/${orgId()}/operations/exceptions?workspace_id=${encodeURIComponent(workspace)}`),
          api<{items: AgentMetric[]}>(`/v1/orgs/${orgId()}/operations/agent-performance?workspace_id=${encodeURIComponent(workspace)}`),
        ]);
        setExceptions(inbox.items);
        setAgents(performance.items);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }
    loadWorkspace();
  }, [workspace]);

  async function cancelExecution(item: ExceptionItem) {
    if (!window.confirm("Request cancellation of this execution? If a provider session has already started, the worker must reconcile and acknowledge the interruption.")) return;
    setCancelling(item.id);
    setError("");
    try {
      const result = await api<{execution_id: string; status: string; error_code: string | null; error_message: string | null}>(
        `/v1/orgs/${orgId()}/executions/${item.id}/cancel?workspace_id=${encodeURIComponent(workspace)}`,
        { method: "POST" },
      );
      setExceptions(current => current.map(row =>
        row.id === item.id && row.kind === "execution" ? { ...row, status: result.status, error_code: result.error_code, error_message: result.error_message } : row
      ));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCancelling("");
    }
  }

  return (
    <Page eyebrow="FOUNDER CONTROL" title="Operations" description="Exceptions, delivery reliability and workforce execution signals.">
      <Notice>Operational views with a founder-governed stop request for retry-wait executions. This screen does not retry jobs or approve protected actions.</Notice>
      <div className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)}>
            {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        {loading ? <div className="empty">Loading operational signals…</div> :
          exceptions.length ? <div className="activity">{exceptions.map(item =>
            <div className="activity-row" key={`${item.kind}:${item.id}`}>
              <span className="activity-dot"/>
              <div>
                <div className="activity-title">{item.title}</div>
                <div className="activity-meta">{item.kind} · {item.status} · {item.created_at ? new Date(item.created_at).toLocaleString() : "Time unavailable"}</div>
                {item.error_message && <div className="activity-meta">{item.error_code || "Execution error"}: {item.error_message}</div>}
                {item.kind === "execution" && item.status === "retry_wait" && <button className="button secondary" disabled={cancelling === item.id} onClick={() => cancelExecution(item)}>{cancelling === item.id ? "Requesting…" : "Stop execution"}</button>}
              </div>
            </div>
          )}</div> : <div className="empty"><strong>No open exceptions</strong>Pending approvals, blocked tasks and failed or retry-wait executions will appear here.</div>}
      </div>
      <div style={{height:16}}/>
      <section className="panel">
        <div className="panel-head"><div className="panel-title">Agent execution reliability</div><span className="panel-note">Execution counts, not quality acceptance</span></div>
        {agents.length ? <div className="activity">{agents.map(a =>
          <div className="activity-row" key={a.agent_id}>
            <span className="activity-dot"/>
            <div>
              <div className="activity-title">{a.name}</div>
              <div className="activity-meta">{a.department} · {a.executions} executions · {a.succeeded} succeeded · {a.failed} failed · {a.active} active · {a.attempts} attempts</div>
            </div>
          </div>
        )}</div> : <div className="empty">No execution history is available for this workspace yet.</div>}
      </section>
    </Page>
  );
}
