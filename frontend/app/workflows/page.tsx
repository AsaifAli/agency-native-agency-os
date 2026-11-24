"use client";

import { useEffect, useState } from "react";
import Page from "@/components/page";
import { api, orgId, Workspace, Execution, AuditEvent } from "@/lib/api";

const statusClass = (status: string) => ["succeeded", "failed", "cancelled"].includes(status) ? status : "pending";

type WorkforceMember = {
  id: string; manager_member_id: string | null; agent_id: string | null;
  member_type: string; name: string; title: string; department_key: string;
  status: string; is_founder_reserved: boolean;
};
type WorkforceCapability = {
  member_id: string; enabled: boolean; allowed_actions: string[];
  allowed_data_classes: string[]; tool_allowlist: string[];
};
type Workforce = { members: WorkforceMember[]; capabilities: WorkforceCapability[] };
type PlanSummary = {
  id: string; objective: string; status: string; task_count: number;
  ready_count: number; blocked_count: number; awaiting_review_count: number;
  failed_count: number; succeeded_count: number; created_at: string; updated_at: string;
};
type PlanTask = {
  ordinal: number; delegation_id: string; child_task_id: string; title: string | null;
  assignee_member_id: string; dependency_task_id: string | null; status: string;
  review_status: string; review_required: boolean; last_error_code: string | null;
};
type PlanDetail = PlanSummary & { root_task_id: string; tasks: PlanTask[] };
type SuggestedTask = {
  title: string;
  description: string;
  department_key: string;
  depends_on_ordinal: number | null;
  acceptance_criteria: string[];
  review_required: true;
};
type PlanDraft = {
  id: string;
  workspace_id: string;
  execution_id: string;
  objective: string;
  plan_title: string;
  status: string;
  suggested_plan: {
    schema_version: 1;
    summary: string;
    tasks: SuggestedTask[];
    risks: string[];
    founder_decisions: string[];
  };
  error_code: string | null;
  approved_plan_id: string | null;
  created_at: string;
  updated_at: string;
};
type AssignmentChoice = {
  value: string;
  managerId: string;
  assigneeId: string;
  label: string;
};
type DraftTask = {
  id: number; title: string; description: string; managerId: string;
  assigneeId: string; dependsOnOrdinal: number | null; reviewRequired: boolean;
};
const executionActions = new Set(["task.execute", "research.execute", "report.generate"]);

export default function Workflows() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selected, setSelected] = useState<Execution | null>(null);
  const [trace, setTrace] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [workforce, setWorkforce] = useState<Workforce>({ members: [], capabilities: [] });
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [planDetail, setPlanDetail] = useState<PlanDetail | null>(null);
  const [objective, setObjective] = useState("");
  const [planTitle, setPlanTitle] = useState("Agency work plan");
  const [draftTasks, setDraftTasks] = useState<DraftTask[]>([]);
  const [nextDraftId, setNextDraftId] = useState(1);
  const [creatingPlan, setCreatingPlan] = useState(false);
  const [planDrafts, setPlanDrafts] = useState<PlanDraft[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [draftObjective, setDraftObjective] = useState("");
  const [draftTitle, setDraftTitle] = useState("Chief of Staff proposal");
  const [draftAssignments, setDraftAssignments] = useState<Record<number, string>>({});
  const [draftWorking, setDraftWorking] = useState(false);

  async function load(workspaceId = workspace) {
    setError("");
    setLoading(true);
    try {
      const [rows, workforceRows, planRows] = await Promise.all([
        api<Execution[]>(`/v1/orgs/${orgId()}/executions?workspace_id=${encodeURIComponent(workspaceId)}&limit=200`),
        api<Workforce>(`/v1/orgs/${orgId()}/workforce?workspace_id=${encodeURIComponent(workspaceId)}`),
        api<PlanSummary[]>(`/v1/orgs/${orgId()}/workforce/plans?workspace_id=${encodeURIComponent(workspaceId)}`),
        api<PlanDraft[]>(`/v1/orgs/${orgId()}/workforce/plan-drafts?workspace_id=${encodeURIComponent(workspaceId)}`),
      ]);
      setExecutions(rows);
      setWorkforce(workforceRows);
      setPlans(planRows);
      setPlanDrafts(planDraftRows);
      const preferredDraft = planDraftRows.some((draft) => draft.id === selectedDraftId)
        ? selectedDraftId : (planDraftRows[0]?.id || "");
      setSelectedDraftId(preferredDraft);
      if (selected && !rows.some((row) => row.id === selected.id)) {
        setSelected(null);
        setTrace([]);
      }
      const preferred = planRows.some((plan) => plan.id === selectedPlanId)
        ? selectedPlanId : (planRows[0]?.id || "");
      setSelectedPlanId(preferred);
      if (preferred) {
        setPlanDetail(await api<PlanDetail>(
          `/v1/orgs/${orgId()}/workforce/plans/${preferred}?workspace_id=${encodeURIComponent(workspaceId)}`,
        ));
      } else {
        setPlanDetail(null);
      }
      const chief = workforceRows.members.find((member) => member.department_key === "office_chief_of_staff");
      if (chief && draftTasks.length === 0) {
        setDraftTasks([{
          id: 1, title: "", description: "", managerId: chief.id,
          assigneeId: "", dependsOnOrdinal: null, reviewRequired: true,
        }]);
        setNextDraftId(2);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }


  const chief = workforce.members.find((member) => member.department_key === "office_chief_of_staff");
  const activeMembers = workforce.members.filter((member) =>
    member.status === "active" && !member.is_founder_reserved
  );
  const eligibleMemberIds = new Set(
    workforce.capabilities.filter((grant) =>
      grant.enabled
      && grant.allowed_actions.some((action) => executionActions.has(action))
      && grant.tool_allowlist.length === 0
      && grant.allowed_data_classes.some((kind) => kind === "synthetic" || kind === "public")
    ).map((grant) => grant.member_id)
  );

  function eligibleReports(managerId: string) {
    return workforce.members.filter((member) =>
      member.manager_member_id === managerId
      && member.status === "active"
      && !member.is_founder_reserved
      && eligibleMemberIds.has(member.id)
    );
  }

  function makeDraftTask(id: number, managerId: string): DraftTask {
    return {
      id, title: "", description: "", managerId,
      assigneeId: eligibleReports(managerId)[0]?.id || "",
      dependsOnOrdinal: null, reviewRequired: true,
    };
  }

  function updateDraftTask(id: number, patch: Partial<DraftTask>) {
    setDraftTasks((current) => current.map((task) => {
      if (task.id !== id) return task;
      const next = { ...task, ...patch };
      if (patch.managerId) next.assigneeId = eligibleReports(patch.managerId)[0]?.id || "";
      return next;
    }));
  }

  function addDraftTask() {
    const previous = draftTasks[draftTasks.length - 1];
    const managerId = previous?.assigneeId || chief?.id || "";
    setDraftTasks((current) => [...current, makeDraftTask(nextDraftId, managerId)]);
    setNextDraftId((value) => value + 1);
  }

  async function createPlan() {
    if (!workspace || !chief || !objective.trim() || draftTasks.length === 0) return;
    setCreatingPlan(true);
    setError("");
    try {
      const result = await api<PlanSummary & { root_task_id: string }>(
        `/v1/orgs/${orgId()}/workforce/plans`,
        {
          method: "POST",
          body: JSON.stringify({
            workspace_id: workspace,
            objective: objective.trim(),
            created_by_member_id: chief.id,
            plan_title: planTitle.trim() || "Agency work plan",
            tasks: draftTasks.map((task) => ({
              workspace_id: workspace,
              parent_task_id: "server-owned-root",
              child_title: task.title.trim(),
              child_description: task.description,
              delegated_by_member_id: task.managerId,
              assigned_to_member_id: task.assigneeId,
              depends_on_ordinal: task.dependsOnOrdinal,
              review_required: task.reviewRequired,
            })),
          }),
        },
      );
      setObjective("");
      setPlanTitle("Agency work plan");
      setDraftTasks([makeDraftTask(1, chief.id)]);
      setNextDraftId(2);
      await load(workspace);
      setSelectedPlanId(result.id);
      setPlanDetail(await api<PlanDetail>(
        `/v1/orgs/${orgId()}/workforce/plans/${result.id}?workspace_id=${encodeURIComponent(workspace)}`,
      ));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreatingPlan(false);
    }
  }

  const selectedDraft = planDrafts.find((draft) => draft.id === selectedDraftId) || null;

  function assignmentChoices(departmentKey: string): AssignmentChoice[] {
    return activeMembers.flatMap((assignee) => {
      const inDepartment = assignee.department_key === departmentKey
        || assignee.department_key === departmentKey + "_head";
      if (!inDepartment || !eligibleMemberIds.has(assignee.id)) return [];
      const manager = workforce.members.find((member) => member.id === assignee.manager_member_id);
      if (!manager || manager.status !== "active" || manager.is_founder_reserved || manager.autonomy_level < 2) {
        return [];
      }
      return [{
        value: manager.id + ":" + assignee.id,
        managerId: manager.id,
        assigneeId: assignee.id,
        label: manager.title + " → " + assignee.title,
      }];
    });
  }

  async function requestPlanDraft() {
    if (!workspace || !draftObjective.trim()) return;
    setDraftWorking(true);
    setError("");
    try {
      const result = await api<PlanDraft>(
        "/v1/orgs/" + orgId() + "/workforce/plan-drafts",
        {
          method: "POST",
          body: JSON.stringify({
            workspace_id: workspace,
            objective: draftObjective.trim(),
            plan_title: draftTitle.trim() || "Chief of Staff proposal",
            idempotency_key: crypto.randomUUID(),
          }),
        },
      );
      setDraftObjective("");
      setSelectedDraftId(result.id);
      setDraftAssignments({});
      await load(workspace);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDraftWorking(false);
    }
  }

  async function refreshPlanDrafts() {
    if (!workspace) return;
    setDraftWorking(true);
    try {
      const rows = await api<PlanDraft[]>(
        "/v1/orgs/" + orgId() + "/workforce/plan-drafts?workspace_id=" + encodeURIComponent(workspace),
      );
      setPlanDrafts(rows);
      if (!rows.some((row) => row.id === selectedDraftId)) {
        setSelectedDraftId(rows[0]?.id || "");
        setDraftAssignments({});
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDraftWorking(false);
    }
  }

  async function approvePlanDraft() {
    if (!workspace || !selectedDraft || selectedDraft.status !== "ready_for_review") return;
    const tasks = selectedDraft.suggested_plan.tasks;
    const assignments = tasks.map((task, index) => {
      const choice = assignmentChoices(task.department_key).find(
        (item) => item.value === draftAssignments[index + 1],
      );
      return choice ? {
        ordinal: index + 1,
        delegated_by_member_id: choice.managerId,
        assigned_to_member_id: choice.assigneeId,
        review_required: true,
      } : null;
    });
    if (assignments.some((item) => item === null)) {
      setError("Choose a direct-manager assignment for every proposed task before approval.");
      return;
    }
    setDraftWorking(true);
    setError("");
    try {
      const result = await api<PlanSummary & { root_task_id: string; draft_status: string }>(
        "/v1/orgs/" + orgId() + "/workforce/plan-drafts/" + selectedDraft.id + "/approve?workspace_id=" + encodeURIComponent(workspace),
        {
          method: "POST",
          body: JSON.stringify({ assignments }),
        },
      );
      await load(workspace);
      setSelectedPlanId(result.id);
      setPlanDetail(await api<PlanDetail>(
        "/v1/orgs/" + orgId() + "/workforce/plans/" + result.id + "?workspace_id=" + encodeURIComponent(workspace),
      ));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDraftWorking(false);
    }
  }

  async function rejectPlanDraft() {
    if (!workspace || !selectedDraft || selectedDraft.status !== "ready_for_review") return;
    setDraftWorking(true);
    setError("");
    try {
      await api(
        "/v1/orgs/" + orgId() + "/workforce/plan-drafts/" + selectedDraft.id + "/reject?workspace_id=" + encodeURIComponent(workspace),
        { method: "POST", body: JSON.stringify({ reason: "Founder rejected the proposed plan." }) },
      );
      await load(workspace);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDraftWorking(false);
    }
  }

  async function refreshPlan() {
    if (!workspace || !selectedPlanId) return;
    try {
      await api(
        `/v1/orgs/${orgId()}/workforce/plans/${selectedPlanId}/refresh?workspace_id=${encodeURIComponent(workspace)}`,
        { method: "POST" },
      );
      await load(workspace);
    } catch (e) { setError((e as Error).message); }
  }

  async function reviewDelegation(delegationId: string) {
    if (!workspace || !selectedPlanId) return;
    try {
      await api(
        `/v1/orgs/${orgId()}/workforce/delegations/${delegationId}/review?workspace_id=${encodeURIComponent(workspace)}&decision=approved`,
        { method: "POST" },
      );
      await load(workspace);
    } catch (e) { setError((e as Error).message); }
  }

  async function requeueDelegation(delegationId: string) {
    if (!workspace || !selectedPlanId) return;
    try {
      await api(
        `/v1/orgs/${orgId()}/workforce/delegations/${delegationId}/requeue?workspace_id=${encodeURIComponent(workspace)}`,
        { method: "POST" },
      );
      await load(workspace);
    } catch (e) { setError((e as Error).message); }
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
    <Page eyebrow="AUTOMATION & COORDINATION" title="Workflows & Chief of Staff" description="Founder-authorized plans, dependency scheduling, execution traces and review gates. The Agency OS retains business state and authorization.">
      <div className="notice">Claude proposal generation is asynchronous, limited to eligible synthetic/public data and tool-free. Plan creation, assignment, requeue and review remain founder-authorized OS actions; external side-effect handlers remain disabled by default.</div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <div className="panel-title">Claude · Chief of Staff proposal</div>
          <span className="panel-note">{planDrafts.length} proposals</span>
        </div>
        <div className="notice">
          Claude proposes a task breakdown only. It cannot assign workforce members, execute tasks or approve its own output. You choose each direct-manager assignment and explicitly approve the resulting plan.
        </div>
        <div className="form-grid" style={{ marginTop: 12 }}>
          <label>Workspace
            <select className="field" value={workspace} onChange={(e) => { setWorkspace(e.target.value); void load(e.target.value); }}>
              {workspaces.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
          <label>Proposal title
            <input className="field" value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} maxLength={200} />
          </label>
          <label className="wide">Founder objective
            <textarea className="field" rows={3} value={draftObjective} onChange={(e) => setDraftObjective(e.target.value)} placeholder="Describe the outcome, constraints and acceptance criteria. Use synthetic or public information only." maxLength={2000} />
          </label>
        </div>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button className="button" onClick={() => void requestPlanDraft()} disabled={!workspace || !draftObjective.trim() || draftWorking || !chief || chief.status !== "active"}>
            {draftWorking ? "Queueing…" : "Ask Claude to prepare a proposal"}
          </button>
          <button className="button secondary" onClick={() => void refreshPlanDrafts()} disabled={!workspace || draftWorking}>Refresh proposals</button>
          <select className="field" value={selectedDraftId} onChange={(e) => { setSelectedDraftId(e.target.value); setDraftAssignments({}); }}>
            <option value="">Select a proposal</option>
            {planDrafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.plan_title} · {draft.status}</option>)}
          </select>
        </div>
        {selectedDraft && (
          <>
            <div className="panel-head" style={{ marginTop: 16 }}>
              <div className="panel-title">{selectedDraft.plan_title}</div>
              <span className={"status " + statusClass(selectedDraft.status)}>{selectedDraft.status}</span>
            </div>
            <div className="activity-meta">{selectedDraft.objective}</div>
            <div className="activity-meta">Execution {selectedDraft.execution_id.slice(0, 12)} · Updated {new Date(selectedDraft.updated_at).toLocaleString()}</div>
            {selectedDraft.error_code && <div className="error">{selectedDraft.error_code}</div>}
            {selectedDraft.status === "queued" || selectedDraft.status === "running"
              ? <div className="empty">Claude is preparing the proposal. Refresh to see the validated result when the worker completes.</div>
              : null}
            {selectedDraft.suggested_plan?.summary && (
              <>
                <div style={{ marginTop: 12 }}>{selectedDraft.suggested_plan.summary}</div>
                {selectedDraft.suggested_plan.risks.length > 0 && (
                  <div className="notice" style={{ marginTop: 10 }}>
                    **Risks to review:** {selectedDraft.suggested_plan.risks.join(" · ")}
                  </div>
                )}
                {selectedDraft.suggested_plan.founder_decisions.length > 0 && (
                  <div className="notice" style={{ marginTop: 10 }}>
                    **Founder decisions:** {selectedDraft.suggested_plan.founder_decisions.join(" · ")}
                  </div>
                )}
                <div className="table-wrap" style={{ marginTop: 12 }}>
                  <table className="data-table">
                    <thead><tr><th>Step</th><th>Work package / acceptance</th><th>Department</th><th>Direct-manager assignment</th></tr></thead>
                    <tbody>
                      {selectedDraft.suggested_plan.tasks.map((task, index) => {
                        const choices = assignmentChoices(task.department_key);
                        return (
                          <tr key={index}>
                            <td>{index + 1}{task.depends_on_ordinal ? <div className="activity-meta">After step {task.depends_on_ordinal}</div> : null}</td>
                            <td>
                              {task.title}
                              <div className="activity-meta">{task.description}</div>
                              {task.acceptance_criteria.map((criterion, criterionIndex) => <div className="activity-meta" key={criterionIndex}>✓ {criterion}</div>)}
                            </td>
                            <td>{task.department_key}</td>
                            <td>
                              <select className="field" value={draftAssignments[index + 1] || ""} disabled={selectedDraft.status !== "ready_for_review"} onChange={(e) => setDraftAssignments((current) => ({ ...current, [index + 1]: e.target.value }))}>
                                <option value="">Choose manager → direct report</option>
                                {choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
                              </select>
                              {!choices.length && <div className="activity-meta">No active, capable reporting pair is available in this department.</div>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {selectedDraft.status === "ready_for_review" && (
                  <div className="toolbar" style={{ marginTop: 12 }}>
                    <button className="button" onClick={() => void approvePlanDraft()} disabled={draftWorking || selectedDraft.suggested_plan.tasks.some((task, index) => !draftAssignments[index + 1] || !assignmentChoices(task.department_key).some((choice) => choice.value === draftAssignments[index + 1]))}>
                      {draftWorking ? "Approving…" : "Approve assignments and create plan"}
                    </button>
                    <button className="button secondary" onClick={() => void rejectPlanDraft()} disabled={draftWorking}>Reject proposal</button>
                  </div>
                )}
                {selectedDraft.status === "approved" && selectedDraft.approved_plan_id && (
                  <div className="notice" style={{ marginTop: 12 }}>Approved plan: {selectedDraft.approved_plan_id}</div>
                )}
              </>
            )}
          </>
        )}
        {!selectedDraft && <div className="empty">No proposal selected. Ask Claude to prepare a bounded plan from a synthetic or public objective.</div>}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <div className="panel-title">Chief of Staff planning</div>
          <span className="panel-note">{chief?.status || "Chief of Staff not provisioned"}</span>
        </div>
        <div className="notice">
          Manual plan authoring remains available as a fallback. Claude-generated proposals are handled separately above and cannot become executable until you approve all assignments.
        </div>
        <div className="form-grid" style={{ marginTop: 12 }}>
          <label>Workspace
            <select className="field" value={workspace} onChange={(e) => { setWorkspace(e.target.value); void load(e.target.value); }}>
              {workspaces.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
          <label>Plan title
            <input className="field" value={planTitle} onChange={(e) => setPlanTitle(e.target.value)} maxLength={200} />
          </label>
          <label className="wide">Founder objective
            <textarea className="field" rows={3} value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Describe the outcome, constraints and acceptance criteria…" maxLength={2000} />
          </label>
        </div>
        <div className="panel-head" style={{ marginTop: 18 }}>
          <div className="panel-title">Delegated work packages</div>
          <span className="panel-note">{draftTasks.length} tasks · dependencies must point to earlier steps</span>
        </div>
        {draftTasks.map((task, index) => {
          const reports = eligibleReports(task.managerId);
          const managers = activeMembers.filter((member) => member.member_type === "supervisor" || member.department_key.endsWith("_head"));
          return (
            <div className="panel" key={task.id} style={{ marginTop: 10 }}>
              <div className="panel-head">
                <div className="panel-title">Step {index + 1}</div>
                {draftTasks.length > 1 && <button className="button secondary" onClick={() => setDraftTasks((rows) => rows.filter((row) => row.id !== task.id))}>Remove</button>}
              </div>
              <div className="form-grid">
                <label className="wide">Task title
                  <input className="field" value={task.title} onChange={(e) => updateDraftTask(task.id, { title: e.target.value })} maxLength={300} />
                </label>
                <label className="wide">Task instructions
                  <textarea className="field" rows={2} value={task.description} onChange={(e) => updateDraftTask(task.id, { description: e.target.value })} maxLength={12000} />
                </label>
                <label>Delegated by
                  <select className="field" value={task.managerId} onChange={(e) => updateDraftTask(task.id, { managerId: e.target.value })}>
                    <option value="">Choose a supervisor</option>
                    {managers.map((member) => <option key={member.id} value={member.id}>{member.title}</option>)}
                  </select>
                </label>
                <label>Assign to direct report
                  <select className="field" value={task.assigneeId} onChange={(e) => updateDraftTask(task.id, { assigneeId: e.target.value })}>
                    <option value="">Choose an active, capable direct report</option>
                    {reports.map((member) => <option key={member.id} value={member.id}>{member.title} · {member.department_key}</option>)}
                  </select>
                </label>
                <label>Depends on
                  <select className="field" value={task.dependsOnOrdinal ?? ""} onChange={(e) => updateDraftTask(task.id, { dependsOnOrdinal: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">No prerequisite</option>
                    {draftTasks.slice(0, index).map((previous, priorIndex) => <option key={previous.id} value={priorIndex + 1}>Step {priorIndex + 1} · {previous.title || "Untitled task"}</option>)}
                  </select>
                </label>
                <label className="check-row">
                  <input type="checkbox" checked={task.reviewRequired} onChange={(e) => updateDraftTask(task.id, { reviewRequired: e.target.checked })} />
                  Founder review required
                </label>
              </div>
            </div>
          );
        })}
        <div className="toolbar" style={{ marginTop: 14 }}>
          <button className="button secondary" onClick={addDraftTask} disabled={draftTasks.length >= 50}>Add delegated task</button>
          <button className="button" onClick={createPlan} disabled={!chief || chief.status !== "active" || !objective.trim() || creatingPlan || !draftTasks.length || draftTasks.some((task) => !task.title.trim() || !task.managerId || !task.assigneeId)}>
            {creatingPlan ? "Creating plan…" : "Create founder-authorized plan"}
          </button>
        </div>
        {chief && chief.status !== "active" && <div className="empty">Activate the Chief of Staff under Founder Authority before creating plans.</div>}
        {!chief && <div className="empty">Provision the workforce chart before creating a plan.</div>}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head"><div className="panel-title">Orchestration plans</div><span className="panel-note">{plans.length} plans</span></div>
        <div className="toolbar">
          <select className="field" value={selectedPlanId} onChange={async (e) => {
            const next = e.target.value;
            setSelectedPlanId(next);
            if (next && workspace) {
              try {
                setPlanDetail(await api<PlanDetail>("/v1/orgs/" + orgId() + "/workforce/plans/" + next + "?workspace_id=" + encodeURIComponent(workspace)));
              } catch (err) { setError((err as Error).message); }
            } else setPlanDetail(null);
          }}>
            <option value="">Select a plan</option>
            {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.objective.slice(0, 70)} · {plan.status}</option>)}
          </select>
          <button className="button secondary" onClick={() => void load(workspace)} disabled={!workspace || loading}>Refresh all</button>
          <button className="button secondary" onClick={refreshPlan} disabled={!selectedPlanId}>Reconcile plan state</button>
        </div>
        {planDetail && (
          <>
            <div className="grid stats" style={{ marginTop: 14 }}>
              <div className="panel"><div className="panel-note">Tasks</div><div className="stat-value">{planDetail.task_count}</div></div>
              <div className="panel"><div className="panel-note">Ready</div><div className="stat-value">{planDetail.ready_count}</div></div>
              <div className="panel"><div className="panel-note">Blocked</div><div className="stat-value">{planDetail.blocked_count}</div></div>
              <div className="panel"><div className="panel-note">Awaiting review</div><div className="stat-value">{planDetail.awaiting_review_count}</div></div>
              <div className="panel"><div className="panel-note">Failed / complete</div><div className="stat-value">{planDetail.failed_count} / {planDetail.succeeded_count}</div></div>
            </div>
            <div className="activity-meta" style={{ marginTop: 10 }}>{planDetail.objective}</div>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data-table">
                <thead><tr><th>Step</th><th>Work package</th><th>Assignee</th><th>Dependency</th><th>Status</th><th>Founder control</th></tr></thead>
                <tbody>
                  {planDetail.tasks.map((task) => {
                    const member = workforce.members.find((row) => row.id === task.assignee_member_id);
                    const dependency = planDetail.tasks.find((row) => row.child_task_id === task.dependency_task_id);
                    return (
                      <tr key={task.delegation_id}>
                        <td>{task.ordinal}</td>
                        <td>{task.title || task.child_task_id.slice(0, 12)}<div className="activity-meta">Task {task.child_task_id.slice(0, 10)}</div></td>
                        <td>{member?.title || task.assignee_member_id.slice(0, 10)}</td>
                        <td>{dependency ? "Step " + dependency.ordinal : "None"}</td>
                        <td><span className={"status " + statusClass(task.status)}>{task.status}</span>{task.last_error_code && <div className="activity-meta">{task.last_error_code}</div>}</td>
                        <td>
                          {task.status === "awaiting_review" && task.review_required
                            ? <button className="button secondary" onClick={() => void reviewDelegation(task.delegation_id)}>Approve result</button> : null}
                          {task.status === "blocked" && task.last_error_code
                            ? <button className="button secondary" onClick={() => void requeueDelegation(task.delegation_id)}>Requeue</button> : null}
                          {task.status === "blocked" && !task.last_error_code ? "Waiting for dependency" : null}
                          {task.status === "succeeded" ? "Complete" : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
        {!planDetail && <div className="empty">No plan selected. Create a founder-authorized plan or select an existing plan.</div>}
      </section>
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
