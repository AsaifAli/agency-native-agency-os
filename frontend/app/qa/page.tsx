"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Page from "@/components/page";
import { api, orgId, type Workspace, type Task } from "@/lib/api";

type Project = { id: string; name: string; status: string };
type EvaluationRun = {
  id: string; task_id: string | null; pack_name: string; score: number;
  passed: boolean; evidence_trust: string; release_eligible: boolean; created_at: string;
};
type QAIssueHistory = {
  id: string; event_type: string; actor_user_id: string | null;
  payload: Record<string, unknown>; created_at: string;
};
type QAIssue = {
  id: string; workspace_id: string; project_id: string; task_id: string;
  title: string; description: string; severity: string; status: string;
  reproducible_steps: string[]; expected_result: string; actual_result: string;
  evidence_references: string[]; assigned_to_user_id: string | null;
  retest_evaluation_run_id: string | null; retest_evidence_trust: string | null;
  fixed_at: string | null; closed_at: string | null; created_at: string; updated_at: string;
};

const nextStep: Record<string, string> = {
  open: "triaged", triaged: "in_progress", in_progress: "fixed", fixed: "retest",
};

function QAIssueCard({ issue, evaluations, workspaceId, onTransition }: {
  issue: QAIssue;
  evaluations: EvaluationRun[];
  workspaceId: string;
  onTransition: (issue: QAIssue, status: string, evaluationId?: string, note?: string) => Promise<void>;
}) {
  const [evaluationId, setEvaluationId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<QAIssueHistory[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const eligibleRuns = evaluations.filter(run =>
    run.task_id === issue.task_id &&
    !!issue.fixed_at &&
    new Date(run.created_at).getTime() > new Date(issue.fixed_at).getTime()
  );
  const passingRuns = eligibleRuns.filter(run => run.passed);
  const failingRuns = eligibleRuns.filter(run => !run.passed);
  const selected = eligibleRuns.find(run => run.id === evaluationId);
  const target = nextStep[issue.status];

  async function move(status: string, runId?: string) {
    setBusy(true);
    try { await onTransition(issue, status, runId, note); setNote(""); setEvaluationId(""); }
    finally { setBusy(false); }
  }

  async function toggleHistory() {
    if (!historyLoaded) {
      try {
        const rows = await api<QAIssueHistory[]>(
          `/v1/orgs/${orgId()}/qa/issues/${issue.id}/history?workspace_id=${encodeURIComponent(workspaceId)}`
        );
        setHistory(rows);
        setHistoryLoaded(true);
        setHistoryError("");
      } catch (error) {
        setHistoryError((error as Error).message);
        return;
      }
    }
    setHistoryOpen(value => !value);
  }

  return (
    <article className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title">{issue.title}</div>
          <div className="activity-meta">Issue {issue.id} · Task {issue.task_id}</div>
        </div>
        <div className="button-row">
          <span className={`status ${issue.severity === "blocker" || issue.severity === "critical" ? "rejected" : "pending"}`}>{issue.severity}</span>
          <span className="status">{issue.status.replaceAll("_", " ")}</span>
        </div>
      </div>
      <p>{issue.description}</p>
      <div className="grid stats">
        <div className="stat"><div className="stat-label">Expected</div><div className="activity-meta">{issue.expected_result || "Not supplied"}</div></div>
        <div className="stat"><div className="stat-label">Actual</div><div className="activity-meta">{issue.actual_result || "Not supplied"}</div></div>
      </div>
      {issue.reproducible_steps.length > 0 && <div style={{ marginTop: 12 }}>
        <div className="stat-label">Reproduction steps</div>
        <ol>{issue.reproducible_steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
      </div>}
      {issue.evidence_references.length > 0 && <div className="activity-meta">Evidence: {issue.evidence_references.join(" · ")}</div>}
      {issue.retest_evaluation_run_id && <div className="activity-meta">Closure retest: {issue.retest_evaluation_run_id} · {issue.retest_evidence_trust || "trust unspecified"}</div>}
      {issue.status !== "closed" && <div className="sub-panel" style={{ marginTop: 14 }}>
        <div className="panel-title">Lifecycle action</div>
        <label className="field">Transition note<textarea value={note} onChange={event => setNote(event.target.value)} rows={2} placeholder="Record the reason or retest observation." /></label>
        {target && <button className="button" disabled={busy} onClick={() => void move(target)}>
          {target === "in_progress" ? "Start work" : target === "retest" ? "Send to retest" : target === "fixed" ? "Mark fixed" : "Triage issue"}
        </button>}
        {issue.status === "retest" && <>
          <label className="field">Retest evaluation
            <select className="field" value={evaluationId} onChange={event => setEvaluationId(event.target.value)}>
              <option value="">Choose a task-linked retest run</option>
              {eligibleRuns.map(run => <option key={run.id} value={run.id}>
                {run.pack_name} · {run.passed ? "passed" : "failed"} · {Math.round(run.score * 100)}% · {run.evidence_trust} · {new Date(run.created_at).toLocaleString()}
              </option>)}
            </select>
            <span className="activity-meta">Only evaluations for this task, created after the fix, are eligible. Self-reported evidence does not certify a release.</span>
          </label>
          <div className="button-row">
            <button className="button" disabled={busy || !selected || !selected.passed || !passingRuns.some(run => run.id === evaluationId)} onClick={() => void move("closed", evaluationId)}>Close with passing retest</button>
            <button className="button secondary" disabled={busy || !selected || selected.passed || !failingRuns.some(run => run.id === evaluationId)} onClick={() => void move("in_progress", evaluationId)}>Retest failed — reopen work</button>
          </div>
        </>}
      </div>}
      {issue.closed_at && <div className="activity-meta" style={{ marginTop: 12 }}>Closed {new Date(issue.closed_at).toLocaleString()}</div>}
      <div style={{ marginTop: 14 }}>
        <button type="button" className="button secondary" onClick={() => void toggleHistory()}>
          {historyOpen ? "Hide audit history" : "Show audit history"}
        </button>
        {historyError && <div className="error" role="alert">{historyError}</div>}
        {historyOpen && <div className="activity" style={{ marginTop: 12 }}>
          {history.map(event => {
            const payload = event.payload;
            const transition = payload.from_status && payload.to_status
              ? `${String(payload.from_status).replaceAll("_", " ")} → ${String(payload.to_status).replaceAll("_", " ")}`
              : String(payload.status || "Issue recorded");
            return <div className="activity-row" key={event.id}>
              <span className="activity-dot" />
              <div>
                <div className="activity-title">{event.event_type.replaceAll("_", " ")} · {transition}</div>
                <div className="activity-meta">{new Date(event.created_at).toLocaleString()} · {event.actor_user_id || "System"}</div>
                {typeof payload.note === "string" && payload.note && <div className="activity-meta">{payload.note}</div>}
                {typeof payload.retest_evaluation_run_id === "string" && <div className="activity-meta">Retest evaluation: {payload.retest_evaluation_run_id} · {String(payload.retest_evidence_trust || "trust not recorded")}</div>}
              </div>
            </div>;
          })}
          {!history.length && <div className="empty">No audit events found.</div>}
        </div>}
      </div>
    </article>
  );
}

export default function QAPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [issues, setIssues] = useState<QAIssue[]>([]);
  const [projectId, setProjectId] = useState("");
  const [taskId, setTaskId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("major");
  const [steps, setSteps] = useState("");
  const [expected, setExpected] = useState("");
  const [actual, setActual] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load(selectedWorkspace = workspaceId) {
    if (!selectedWorkspace) return;
    const [projectRows, taskRows, evalRows, issueRows] = await Promise.all([
      api<Project[]>(`/v1/orgs/${orgId()}/projects?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
      api<Task[]>(`/v1/orgs/${orgId()}/tasks?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
      api<EvaluationRun[]>(`/v1/orgs/${orgId()}/evaluations?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
      api<QAIssue[]>(`/v1/orgs/${orgId()}/qa/issues?workspace_id=${encodeURIComponent(selectedWorkspace)}`),
    ]);
    setProjects(projectRows);
    setTasks(taskRows);
    setEvaluations(evalRows);
    setIssues(issueRows);
    setProjectId(current => projectRows.some(row => row.id === current) ? current : projectRows[0]?.id || "");
    setTaskId(current => taskRows.some(row => row.id === current) ? current : taskRows[0]?.id || "");
  }

  useEffect(() => {
    async function init() {
      if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID first.");
      const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
      setWorkspaces(rows);
      const selected = rows[0]?.id || "";
      setWorkspaceId(selected);
      if (selected) await load(selected);
    }
    init().catch(error => setError(error.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createIssue(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      await api(`/v1/orgs/${orgId()}/qa/issues`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId, project_id: projectId, task_id: taskId,
          title, description, severity,
          reproducible_steps: steps.split("\n").map(value => value.trim()).filter(Boolean),
          expected_result: expected, actual_result: actual,
          evidence_references: evidence.split("\n").map(value => value.trim()).filter(Boolean),
        }),
      });
      setTitle(""); setDescription(""); setSteps(""); setExpected(""); setActual(""); setEvidence("");
      setNotice("QA issue recorded.");
      await load(workspaceId);
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }

  async function transition(issue: QAIssue, status: string, evaluationId?: string, note?: string) {
    setError(""); setNotice("");
    try {
      await api(`/v1/orgs/${orgId()}/qa/issues/${issue.id}/transition?workspace_id=${encodeURIComponent(workspaceId)}`, {
        method: "PATCH",
        body: JSON.stringify({ status, retest_evaluation_run_id: evaluationId || null, note: note || "" }),
      });
      setNotice(`Issue moved to ${status.replaceAll("_", " ")}.`);
      await load(workspaceId);
    } catch (error) { setError((error as Error).message); }
  }

  return (
    <Page eyebrow="QUALITY & DELIVERY CONTROL" title="QA & Defects" description="Track reproducible defects against delivery tasks, preserve the lifecycle history, and require task-linked retest evidence before closure.">
      <div className="panel">
        <div className="panel-head"><div className="panel-title">Workspace QA register</div><span className="panel-note">{issues.length} issues</span></div>
        <label className="field">Workspace
          <select className="field" value={workspaceId} onChange={event => {
            const selected = event.target.value; setWorkspaceId(selected);
            setIssues([]); setProjects([]); setTasks([]); setEvaluations([]);
            load(selected).catch(error => setError(error.message));
          }}>
            {workspaces.map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
          </select>
        </label>
        <div className="grid stats">
          {(["open", "in_progress", "retest", "closed"] as const).map(status => (
            <div className="stat" key={status}><div className="stat-label">{status.replaceAll("_", " ")}</div><div className="stat-value">{issues.filter(issue => issue.status === status).length}</div></div>
          ))}
        </div>
      </div>
      <div style={{ height: 16 }} />
      <div className="panel">
        <div className="panel-head"><div className="panel-title">Record a QA issue</div></div>
        <form className="form-grid" onSubmit={createIssue}>
          <label className="field">Project<select className="field" required value={projectId} onChange={event => setProjectId(event.target.value)}>
            <option value="">Select project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select></label>
          <label className="field">Related task<select className="field" required value={taskId} onChange={event => setTaskId(event.target.value)}>
            <option value="">Select task</option>{tasks.map(task => <option key={task.id} value={task.id}>{task.title}</option>)}
          </select></label>
          <label className="field wide">Issue title<input className="field" required minLength={3} maxLength={240} value={title} onChange={event => setTitle(event.target.value)} /></label>
          <label className="field wide">Description<textarea className="field" required minLength={3} value={description} onChange={event => setDescription(event.target.value)} rows={3} /></label>
          <label className="field">Severity<select className="field" value={severity} onChange={event => setSeverity(event.target.value)}>
            {["blocker", "critical", "major", "minor", "cosmetic"].map(value => <option key={value} value={value}>{value}</option>)}
          </select></label>
          <label className="field">Reproducible steps<textarea className="field" value={steps} onChange={event => setSteps(event.target.value)} rows={3} placeholder="One step per line" /></label>
          <label className="field">Expected result<textarea className="field" value={expected} onChange={event => setExpected(event.target.value)} rows={2} /></label>
          <label className="field">Actual result<textarea className="field" value={actual} onChange={event => setActual(event.target.value)} rows={2} /></label>
          <label className="field wide">Evidence references<textarea className="field" value={evidence} onChange={event => setEvidence(event.target.value)} rows={2} placeholder="Artifact or evidence reference, one per line" /></label>
          <div className="wide"><button className="button" disabled={busy || !workspaceId || !projectId || !taskId}>{busy ? "Recording…" : "Record issue"}</button></div>
        </form>
        {error && <div className="error" role="alert">{error}</div>}
        {notice && <div className="activity-meta" role="status">{notice}</div>}
      </div>
      <div style={{ height: 16 }} />
      <div style={{ display: "grid", gap: 16 }}>
        {issues.map(issue => <QAIssueCard key={issue.id} issue={issue} evaluations={evaluations} workspaceId={workspaceId} onTransition={transition} />)}
        {!issues.length && <div className="panel empty">No QA issues recorded in this workspace.</div>}
      </div>
    </Page>
  );
}
