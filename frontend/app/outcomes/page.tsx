"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Project = { id: string; workspace_id: string; name: string; status: string };
type Milestone = { id: string; title: string; status: string };
type EvaluationRun = { id: string; pack_name: string; score: number; passed: boolean; evidence_trust: string; release_eligible: boolean; created_at: string };
type Measurement = {
  id: string; outcome_id: string; value: string; measured_at: string; source_type: string;
  source_reference: string; evidence_summary: string; milestone_id: string | null;
  supporting_evaluation_run_id: string | null;
};
type OutcomeRecord = {
  id: string; workspace_id: string; project_id: string; title: string;
  problem_statement: string; desired_outcome: string; metric_name: string;
  metric_unit: string; direction: "increase" | "decrease";
  baseline_value: string | null; target_value: string; target_date: string | null;
  measurement_method: string; acceptance_criteria: string[];
  delivery_acceptance_status: "pending" | "accepted" | "rejected";
  acceptance_results: Record<string, boolean>; acceptance_note: string;
  latest_value: string | null; latest_measured_at: string | null;
  measurement_count: number; impact_status: "not_measured" | "target_met" | "target_missed";
};
type Outcome = OutcomeRecord & { measurements: Measurement[] };
type OutcomeDraft = {
  title: string; problem_statement: string; desired_outcome: string;
  metric_name: string; metric_unit: string; direction: "increase" | "decrease";
  baseline_value: string; target_value: string; target_date: string;
  measurement_method: string; acceptance_criteria: string;
};
const emptyDraft: OutcomeDraft = {
  title: "", problem_statement: "", desired_outcome: "", metric_name: "",
  metric_unit: "", direction: "decrease", baseline_value: "", target_value: "",
  target_date: "", measurement_method: "", acceptance_criteria: "",
};

function OutcomeCard({ outcome, milestones, evaluations, onMeasure, onDecide }: {
  outcome: Outcome;
  milestones: Milestone[];
  evaluations: EvaluationRun[];
  onMeasure: (id: string, data: { value: string; source_type: string; source_reference: string; evidence_summary: string; milestone_id: string | null; supporting_evaluation_run_id: string | null }) => Promise<void>;
  onDecide: (id: string, decision: "accepted" | "rejected", results: Record<string, boolean>, note: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [sourceType, setSourceType] = useState("client_reported");
  const [sourceReference, setSourceReference] = useState("");
  const [evidence, setEvidence] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [evaluationId, setEvaluationId] = useState("");
  const [criteria, setCriteria] = useState<Record<string, boolean>>(
    Object.fromEntries(outcome.acceptance_criteria.map(item => [item, outcome.acceptance_results[item] ?? false]))
  );
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const allMet = outcome.acceptance_criteria.every(item => criteria[item] === true);
  const status = outcome.impact_status === "target_met" ? "Target met" :
    outcome.impact_status === "target_missed" ? "Latest measurement below target" : "Not measured";

  async function measure(e: FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await onMeasure(outcome.id, { value, source_type: sourceType, source_reference: sourceReference, evidence_summary: evidence, milestone_id: milestoneId || null, supporting_evaluation_run_id: evaluationId || null }); setValue(""); setSourceReference(""); setEvidence(""); setMilestoneId(""); setEvaluationId(""); }
    finally { setBusy(false); }
  }
  async function decide(decision: "accepted" | "rejected") {
    setBusy(true);
    try { await onDecide(outcome.id, decision, criteria, note); }
    finally { setBusy(false); }
  }

  return <article className="panel">
    <div className="panel-head">
      <div><div className="panel-title">{outcome.title}</div><div className="activity-meta">{outcome.metric_name} · {outcome.metric_unit}</div></div>
      <span className={`status ${outcome.impact_status === "target_met" ? "approved" : "pending"}`}>{status}</span>
    </div>
    <p>{outcome.desired_outcome}</p>
    <div className="grid stats">
      <div className="stat"><div className="stat-label">Baseline</div><div className="stat-value">{outcome.baseline_value ?? "—"} {outcome.metric_unit}</div></div>
      <div className="stat"><div className="stat-label">Target</div><div className="stat-value">{outcome.direction === "decrease" ? "≤" : "≥"} {outcome.target_value} {outcome.metric_unit}</div></div>
      <div className="stat"><div className="stat-label">Latest</div><div className="stat-value">{outcome.latest_value ?? "—"} {outcome.latest_value ? outcome.metric_unit : ""}</div></div>
      <div className="stat"><div className="stat-label">Measurements</div><div className="stat-value">{outcome.measurement_count}</div></div>
    </div>
    <div className="activity-meta">Delivery acceptance: <strong>{outcome.delivery_acceptance_status.replaceAll("_", " ")}</strong>{outcome.latest_measured_at ? ` · measured ${new Date(outcome.latest_measured_at).toLocaleDateString()}` : ""}</div>
    {outcome.delivery_acceptance_status === "pending" && <section className="sub-panel" style={{ marginTop: 14 }}>
      <div className="panel-title">Founder delivery acceptance</div>
      <p className="activity-meta">Review every agreed criterion. Acceptance is separate from later business-impact measurement.</p>
      {outcome.acceptance_criteria.map(item => <label className="check-row" key={item}>
        <input type="checkbox" checked={criteria[item] ?? false} onChange={e => setCriteria(old => ({ ...old, [item]: e.target.checked }))} />
        <span>{item}</span>
      </label>)}
      <label className="field">Decision note<textarea value={note} onChange={e => setNote(e.target.value)} minLength={10} placeholder="Record the evidence and rationale (at least 10 characters)." /></label>
      <div className="button-row">
        <button className="button" disabled={busy || !allMet || note.trim().length < 10} onClick={() => void decide("accepted")}>Accept delivery</button>
        <button className="button secondary" disabled={busy || allMet || note.trim().length < 10} onClick={() => void decide("rejected")}>Reject delivery</button>
      </div>
    </section>}
    <details style={{ marginTop: 14 }}>
      <summary className="panel-title">Measurement history ({outcome.measurements.length})</summary>
      {outcome.measurements.length ? <div className="activity" style={{ marginTop: 12 }}>{outcome.measurements.map(row =>
        <div className="activity-row" key={row.id}>
          <span className="activity-dot"/>
          <div><div className="activity-title">{row.value} · {row.source_type.replaceAll("_", " ")}</div>
            <div className="activity-meta">{new Date(row.measured_at).toLocaleString()} · {row.source_reference}</div>
            {row.milestone_id && <div className="activity-meta">Milestone: {milestones.find(item => item.id === row.milestone_id)?.title || "Linked milestone"}</div>}
            {row.supporting_evaluation_run_id && <div className="activity-meta">Evaluation run: {evaluations.find(item => item.id === row.supporting_evaluation_run_id)?.pack_name || "Linked evaluation"} · {row.supporting_evaluation_run_id}</div>}
            <div className="activity-meta">{row.evidence_summary}</div>
          </div>
        </div>
      )}</div> : <div className="empty">No measurement evidence recorded yet.</div>}
    </details>
    <details style={{ marginTop: 14 }}>
      <summary className="panel-title">Record a business-impact measurement</summary>
      <form onSubmit={measure} className="form-grid" style={{ marginTop: 12 }}>
        <label className="field">Measured value<input type="number" step="any" required value={value} onChange={e => setValue(e.target.value)} /></label>
        <label className="field">Evidence source<select value={sourceType} onChange={e => setSourceType(e.target.value)}>
          <option value="client_reported">Client reported</option><option value="agency_measured">Agency measured</option><option value="system_measured">System measured</option>
        </select></label>
        <label className="field">Related milestone<select value={milestoneId} onChange={e => setMilestoneId(e.target.value)}><option value="">No milestone link</option>{milestones.map(item => <option key={item.id} value={item.id}>{item.title} · {item.status}</option>)}</select></label>
        <label className="field">Supporting evaluation run<select value={evaluationId} onChange={e => setEvaluationId(e.target.value)}><option value="">No evaluation link</option>{evaluations.map(item => <option key={item.id} value={item.id}>{item.pack_name} · {item.passed ? "passed" : "failed"} · {Math.round(item.score * 100)}% · {item.evidence_trust}</option>)}</select><span className="activity-meta">Evaluation runs are supporting, self-reported evidence unless independently verified. They are not release approval.</span></label>
        <label className="field">Source reference<input required minLength={2} maxLength={240} value={sourceReference} onChange={e => setSourceReference(e.target.value)} placeholder="Report, dashboard, dataset or evidence ID" /></label>
        <label className="field">Evidence summary<textarea required minLength={10} value={evidence} onChange={e => setEvidence(e.target.value)} placeholder="What was measured, over what period, and how?" /></label>
        <button className="button" disabled={busy}>Save measurement</button>
      </form>
    </details>
  </article>;
}

export default function OutcomesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [projectName, setProjectName] = useState("");
  const [draft, setDraft] = useState<OutcomeDraft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadOutcomeRows(selectedProject: string, selectedWorkspace: string) {
    const [rows, measurements, projectMilestones] = await Promise.all([
      api<OutcomeRecord[]>(`/v1/orgs/${orgId()}/projects/${selectedProject}/outcomes?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
      api<Measurement[]>(`/v1/orgs/${orgId()}/projects/${selectedProject}/outcome-measurements?workspace_id=${encodeURIComponent(selectedWorkspace)}&limit=1000`),
      api<Milestone[]>(`/v1/orgs/${orgId()}/projects/${selectedProject}/milestones?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
      api<EvaluationRun[]>(`/v1/orgs/${orgId()}/evaluations?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
    ]);
    setMilestones(projectMilestones);
    setEvaluations(projectEvaluations);
    const byOutcome = new Map<string, Measurement[]>();
    for (const measurement of measurements) {
      const current = byOutcome.get(measurement.outcome_id) || [];
      if (current.length < 25) current.push(measurement);
      byOutcome.set(measurement.outcome_id, current);
    }
    setOutcomes(rows.map(outcome => ({ ...outcome, measurements: byOutcome.get(outcome.id) || [] })));
  }

  async function loadProjects(selectedWorkspace = workspaceId) {
    if (!selectedWorkspace) return;
    const rows = await api<Project[]>(`/v1/orgs/${orgId()}/projects?workspace_id=${encodeURIComponent(selectedWorkspace)}`);
    setProjects(rows);
    const chosen = rows.some(row => row.id === projectId) ? projectId : rows[0]?.id || "";
    setProjectId(chosen);
    if (chosen) await loadOutcomeRows(chosen, selectedWorkspace);
    else setOutcomes([]);
  }

  useEffect(() => {
    async function init() {
      try {
        if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
        setWorkspaces(rows);
        const chosen = rows[0]?.id || "";
        setWorkspaceId(chosen);
        if (chosen) {
          const items = await api<Project[]>(`/v1/orgs/${orgId()}/projects?workspace_id=${encodeURIComponent(chosen)}`);
          setProjects(items);
          const selected = items[0]?.id || "";
          setProjectId(selected);
          if (selected) await loadOutcomeRows(selected, chosen);
        }
      } catch (e) { setError((e as Error).message); }
    }
    void init();
  }, []);

  async function refresh() {
    if (projectId && workspaceId) await loadOutcomeRows(projectId, workspaceId);
  }

  async function createProject(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const row = await api<Project>(`/v1/orgs/${orgId()}/projects`, { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, name: projectName }) });
      setProjectName(""); setNotice("Project created."); await loadProjects(workspaceId); setProjectId(row.id); setOutcomes([]);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function createOutcome(e: FormEvent) {
    e.preventDefault(); if (!projectId) return; setBusy(true); setError(""); setNotice("");
    try {
      await api(`/v1/orgs/${orgId()}/projects/${projectId}/outcomes`, { method: "POST", body: JSON.stringify({
        workspace_id: workspaceId, ...draft,
        baseline_value: draft.baseline_value || null,
        target_date: draft.target_date ? `${draft.target_date}T00:00:00Z` : null,
        acceptance_criteria: draft.acceptance_criteria.split("\n").map(v => v.trim()).filter(Boolean),
      }) });
      setDraft(emptyDraft); setNotice("Agreed outcome and acceptance criteria recorded."); await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function recordMeasurement(id: string, data: { value: string; source_type: string; source_reference: string; evidence_summary: string; milestone_id: string | null; supporting_evaluation_run_id: string | null }) {
    setError(""); setNotice("");
    try {
      await api(`/v1/orgs/${orgId()}/outcomes/${id}/measurements`, { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, ...data }) });
      setNotice("Measurement recorded as append-only evidence."); await refresh();
    } catch (e) { setError((e as Error).message); }
  }

  async function decideAcceptance(id: string, decision: "accepted" | "rejected", criteria_results: Record<string, boolean>, note: string) {
    setError(""); setNotice("");
    try {
      await api(`/v1/orgs/${orgId()}/outcomes/${id}/acceptance`, { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, decision, criteria_results, note }) });
      setNotice(`Delivery ${decision}; decision recorded in the audit trail.`); await refresh();
    } catch (e) { setError((e as Error).message); }
  }

  return <Page eyebrow="RESULTS AS A SERVICE" title="Client Outcomes" description="Track agreed business results separately from delivery completion and QA evidence.">
    <Notice>Tasks, milestones and evaluation runs are supporting evidence—not proof of client impact. Measurements require a source and explanation; founder authority is required for delivery acceptance.</Notice>
    {error && <div className="error">{error}</div>}{notice && <div className="notice">{notice}</div>}
    <section className="panel">
      <div className="panel-head"><div className="panel-title">Workspace and project</div></div>
      <div className="two-col">
        <label className="field">Workspace<select value={workspaceId} onChange={async e => { const id = e.target.value; setWorkspaceId(id); setProjectId(""); setOutcomes([]); try { await loadProjects(id); } catch (err) { setError((err as Error).message); } }}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
        <label className="field">Project<select value={projectId} onChange={async e => { const id = e.target.value; setProjectId(id); try { if (id) await loadOutcomeRows(id, workspaceId); else setOutcomes([]); } catch (err) { setError((err as Error).message); } }}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      </div>
      <form onSubmit={createProject} className="inline-form">
        <label className="field">New project<input required minLength={2} maxLength={240} value={projectName} onChange={e => setProjectName(e.target.value)} placeholder="e.g. Customer support automation" /></label>
        <button className="button" disabled={!workspaceId || busy}>Create project</button>
      </form>
    </section>
    {projectId && <section className="panel" style={{ marginTop: 16 }}>
      <div className="panel-head"><div className="panel-title">Define an agreed outcome</div></div>
      <form onSubmit={createOutcome} className="form-grid">
        <label className="field">Outcome title<input required minLength={3} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
        <label className="field">Metric name<input required value={draft.metric_name} onChange={e => setDraft({ ...draft, metric_name: e.target.value })} placeholder="Average handling time" /></label>
        <label className="field">Problem statement<textarea required minLength={10} value={draft.problem_statement} onChange={e => setDraft({ ...draft, problem_statement: e.target.value })} /></label>
        <label className="field">Desired outcome<textarea required minLength={10} value={draft.desired_outcome} onChange={e => setDraft({ ...draft, desired_outcome: e.target.value })} /></label>
        <div className="two-col">
          <label className="field">Unit<input required value={draft.metric_unit} onChange={e => setDraft({ ...draft, metric_unit: e.target.value })} placeholder="minutes, %, INR" /></label>
          <label className="field">Direction<select value={draft.direction} onChange={e => setDraft({ ...draft, direction: e.target.value as "increase" | "decrease" })}><option value="decrease">Decrease (at or below target)</option><option value="increase">Increase (at or above target)</option></select></label>
        </div>
        <div className="two-col">
          <label className="field">Baseline (optional)<input type="number" step="any" value={draft.baseline_value} onChange={e => setDraft({ ...draft, baseline_value: e.target.value })} /></label>
          <label className="field">Target value<input type="number" step="any" required value={draft.target_value} onChange={e => setDraft({ ...draft, target_value: e.target.value })} /></label>
        </div>
        <label className="field">Target date (optional)<input type="date" value={draft.target_date} onChange={e => setDraft({ ...draft, target_date: e.target.value })} /></label>
        <label className="field">Measurement method<textarea required minLength={10} value={draft.measurement_method} onChange={e => setDraft({ ...draft, measurement_method: e.target.value })} placeholder="Define the data source, period and calculation." /></label>
        <label className="field">Delivery acceptance criteria (one per line)<textarea required value={draft.acceptance_criteria} onChange={e => setDraft({ ...draft, acceptance_criteria: e.target.value })} placeholder={"Agreed workflow passes QA and security checks.\nClient team completes acceptance testing."} /></label>
        <button className="button" disabled={busy}>Save agreed outcome</button>
      </form>
    </section>}
    <section style={{ marginTop: 16 }}>
      <div className="panel-head"><div className="panel-title">Outcome scorecard</div><span className="panel-note">{outcomes.length} outcomes</span></div>
      {outcomes.length ? <div className="stack">{outcomes.map(outcome => <OutcomeCard key={outcome.id} outcome={outcome} milestones={milestones} evaluations={evaluations} onMeasure={recordMeasurement} onDecide={decideAcceptance} />)}</div> : <div className="panel empty"><strong>No outcomes defined</strong>Select a project and record its first agreed business outcome.</div>}
    </section>
  </Page>;
}
