"use client";

import { useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId } from "@/lib/api";

type Pack = { name: string; description: string; tags: string[]; gate_count: number; metric_count: number };
type Evaluation = {
  id: string; workspace_id: string; task_id?: string | null; pack_name: string;
  score: number; passed: boolean; metrics: Record<string, number>;
  gate_results: Record<string, { threshold: number; actual: number; passed: boolean }>;
  created_at: string;
};
type Workspace = { id: string; name: string };

export default function Evaluations() {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [runs, setRuns] = useState<Evaluation[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [selectedPack, setSelectedPack] = useState("agent_workflow");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    if (!orgId()) { setError("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local."); return; }
    try {
      const [ws, catalog] = await Promise.all([
        api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`),
        api<{ packs: Pack[] }>(`/v1/evaluations/packs?org_id=${orgId()}`)
      ]);
      setWorkspaces(ws); setPacks(catalog.packs);
      const chosen = workspaceId || ws[0]?.id || "";
      setWorkspaceId(chosen);
      if (chosen) setRuns(await api<Evaluation[]>(`/v1/orgs/${orgId()}/evaluations?workspace_id=${chosen}`));
    } catch (e) { setError((e as Error).message); }
  }

  useEffect(() => { void load(); }, []);

  async function runSample() {
    if (!workspaceId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const sample = selectedPack === "rag" ? {
        expected: { relevant_documents: ["doc-a", "doc-b"], required_citations: ["source-a"], relevant_citations: ["source-a"] },
        actual: { retrieved_documents: ["doc-a", "doc-b"], citations: ["source-a"], answer_relevance: 1, groundedness: 1 }
      } : {
        expected: { required_steps: ["plan", "execute"] },
        actual: { status: "completed", completed_steps: ["plan", "execute"], tool_call_validity: 1, policy_pass_rate: 1, approval_compliant: true, execution_reliability: 1, fallback_rate: 0 }
      };
      await api<Evaluation>(`/v1/orgs/${orgId()}/evaluations`, {
        method: "POST", body: JSON.stringify({ workspace_id: workspaceId, pack_name: selectedPack, ...sample })
      });
      setNotice("Synthetic evaluation completed and recorded in the OS audit trail.");
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return <Page eyebrow="QUALITY ENGINEERING" title="Evaluations" description="Harness-backed RAG and agent workflow quality gates, persisted as tenant-scoped OS records.">
    <Notice>Only synthetic sample runs are enabled in this slice. No client data is sent to an external model or evaluator.</Notice>
    {error && <div className="error">{error}</div>}
    {notice && <div className="notice">{notice}</div>}
    <section className="panel">
      <div className="panel-head"><div className="panel-title">Evaluation packs</div><span className="panel-note">{packs.length} active</span></div>
      {packs.length ? <div className="grid stats">{packs.map(pack => <div className="panel" key={pack.name}>
        <div className="activity-title">{pack.name.replaceAll("_", " ")}</div>
        <p className="activity-meta">{pack.description}</p>
        <div className="activity-meta">{pack.gate_count} gates · {pack.metric_count} metrics</div>
      </div>)}</div> : <div className="empty">Loading evaluation pack catalog…</div>}
      <div className="two-col" style={{ marginTop: 16 }}>
        <label className="field">Workspace<select value={workspaceId} onChange={e => setWorkspaceId(e.target.value)}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
        <label className="field">Pack<select value={selectedPack} onChange={e => setSelectedPack(e.target.value)}>{packs.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}</select></label>
      </div>
      <button className="button" disabled={!workspaceId || busy} onClick={runSample}>{busy ? "Running…" : "Run synthetic evaluation"}</button>
    </section>
    <section className="panel" style={{ marginTop: 16 }}>
      <div className="panel-head"><div className="panel-title">Recent evaluation runs</div><span className="panel-note">{runs.length} records</span></div>
      {runs.length ? <div className="activity">{runs.map(run => <div className="activity-row" key={run.id}>
        <span className={`status ${run.passed ? "success" : "pending"}`}>{run.passed ? "Passed" : "Failed"}</span>
        <div style={{ flex: 1 }}><div className="activity-title">{run.pack_name} · {(run.score * 100).toFixed(1)}%</div>
          <div className="activity-meta">{new Date(run.created_at).toLocaleString()} · {Object.keys(run.metrics).length} metrics · {Object.values(run.gate_results).filter(g => g.passed).length}/{Object.keys(run.gate_results).length} gates</div>
        </div>
      </div>)}</div> : <div className="empty"><strong>No evaluation runs yet</strong>Run a synthetic evaluation to verify the integrated Harness service.</div>}
    </section>
  </Page>;
}
