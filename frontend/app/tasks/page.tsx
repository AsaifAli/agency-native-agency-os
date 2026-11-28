"use client";

import { useEffect, useState } from "react";
import Page from "@/components/page";
import { api, orgId, type Workspace, type Task } from "@/lib/api";

type Project = { id: string; name: string };
type Milestone = { id: string; project_id: string; title: string; status: string };

export default function Tasks() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [items, setItems] = useState<Task[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [title, setTitle] = useState("Audit Command Center execution boundary");
  const [description, setDescription] = useState("Map reusable execution code to the OS runtime adapter.");
  const [err, setErr] = useState("");

  async function load(selectedWorkspace?: string) {
    const available = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
    setWorkspaces(available);
    const wid = selectedWorkspace || workspace || available[0]?.id || "";
    if (!wid) {
      setItems([]);
      setMilestones([]);
      setWorkspace("");
      return;
    }
    setWorkspace(wid);
    const [tasks, projects] = await Promise.all([
      api<Task[]>(`/v1/orgs/${orgId()}/tasks?workspace_id=${encodeURIComponent(wid)}`),
      api<Project[]>(`/v1/orgs/${orgId()}/projects?workspace_id=${encodeURIComponent(wid)}`),
    ]);
    const projectMilestones = await Promise.all(
      projects.map(project =>
        api<Milestone[]>(
          `/v1/orgs/${orgId()}/projects/${project.id}/milestones?workspace_id=${encodeURIComponent(wid)}`
        )
      )
    );
    setItems(tasks);
    setMilestones(projectMilestones.flat());
    setMilestoneId(current => projectMilestones.flat().some(item => item.id === current) ? current : "");
  }

  useEffect(() => {
    if (orgId()) load().catch(e => setErr(e.message));
    else setErr("Set NEXT_PUBLIC_ORG_ID first.");
    // Initial load only; workspace changes are loaded explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create() {
    try {
      await api(`/v1/orgs/${orgId()}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          title,
          description,
          milestone_id: milestoneId || null,
        }),
      });
      setMilestoneId("");
      await load(workspace);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const milestoneLabel = (id: string) => {
    const item = milestones.find(m => m.id === id);
    return item ? item.title : "Unlinked";
  };

  return (
    <Page eyebrow="DELIVERY MANAGEMENT" title="Tasks" description="Create and track work owned by the Agency OS, linked to the milestone it contributes to.">
      <div className="panel">
        <div className="panel-head"><div className="panel-title">Create task</div></div>
        <div className="form-grid">
          <label className="wide">Title<input className="field" value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label className="wide">Description<textarea className="field" rows={3} value={description} onChange={e => setDescription(e.target.value)} /></label>
          <label className="wide">Workspace
            <select className="field" value={workspace} onChange={e => load(e.target.value).catch(error => setErr(error.message))}>
              {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </label>
          <label className="wide">Related project milestone
            <select className="field" value={milestoneId} onChange={e => setMilestoneId(e.target.value)}>
              <option value="">No milestone link</option>
              {milestones.map(m => <option key={m.id} value={m.id}>{m.title} · {m.status}</option>)}
            </select>
            <span className="activity-meta">Only milestones in the selected workspace are available.</span>
          </label>
        </div>
        <div style={{ marginTop: 14 }}><button className="button" onClick={create} disabled={!workspace || !title.trim()}>Create task</button></div>
        {err && <div className="error">{err}</div>}
      </div>
      <div style={{ height: 16 }} />
      <div className="panel">
        <div className="panel-head"><div className="panel-title">Task register</div><span className="panel-note">{items.length} tasks</span></div>
        <table className="data-table">
          <thead><tr><th>Task</th><th>Milestone</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>{items.map(t => <tr key={t.id}>
            <td>{t.title}<div className="activity-meta">{t.description}</div></td>
            <td>{t.milestone_id ? milestoneLabel(t.milestone_id) : "Unlinked"}</td>
            <td><span className="status">{t.status}</span></td>
            <td>{new Date(t.created_at).toLocaleDateString()}</td>
          </tr>)}</tbody>
        </table>
        {!items.length && <div className="empty">No tasks created yet.</div>}
      </div>
    </Page>
  );
}
