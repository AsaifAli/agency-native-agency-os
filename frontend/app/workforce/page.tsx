"use client";

import { useEffect, useMemo, useState } from "react";
import Page from "@/components/page";
import { api, orgId, Workspace } from "@/lib/api";

type Unit = {
  id: string;
  parent_unit_id: string | null;
  name: string;
  unit_type: "office" | "group" | "department" | "team";
  department_key: string;
  description: string;
};
type Member = {
  id: string;
  unit_id: string | null;
  manager_member_id: string | null;
  agent_id: string | null;
  member_type: "human" | "agent" | "supervisor" | "sub_agent";
  name: string;
  title: string;
  department_key: string;
  responsibilities: string[];
  autonomy_level: number;
  status: "planned" | "active" | "paused" | "retired";
  is_founder_reserved: boolean;
};
type Capability = {
  id: string;
  member_id: string;
  capability_key: string;
  enabled: boolean;
  allowed_actions: string[];
  allowed_data_classes: string[];
  tool_allowlist: string[];
};
type Position = {
  id: string;
  unit_id: string | null;
  team_unit_id: string | null;
  assigned_member_id: string | null;
  position_key: string;
  title: string;
  department_key: string;
  group_key: string;
  team_key: string;
  reports_to_position_key: string | null;
  responsibilities: string[];
  autonomy_ceiling: number;
  status: string;
};
type Workforce = { units: Unit[]; members: Member[]; capabilities: Capability[]; positions: Position[] };
type Specialist = { specialist_key: string; title: string; department_key: string; runtime_owner: "claude"; profile_ref: string; status: "catalogued"; default_enabled: false };
type BlueprintTask = { specialist_key: string; department_key: string; title: string; objective: string; inputs: string[]; outputs: string[]; review_required: true };
type TeamBlueprint = { slug: string; title: string; summary: string; duration_hint: string; schema_version: number; groups: { group: string; activation: string; tasks: BlueprintTask[] }[] };

const GROUP_ORDER = [
  "Growth",
  "Strategy & Commercial",
  "Technology & Innovation",
  "Execution & Quality",
  "Business Operations & Relationships",
];

export default function WorkforcePage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [workforce, setWorkforce] = useState<Workforce>({ units: [], members: [], capabilities: [], positions: [] });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [blueprints, setBlueprints] = useState<TeamBlueprint[]>([]);

  async function load(selected = workspaceId) {
    setLoading(true);
    setError("");
    try {
      const available = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
      setWorkspaces(available);
      const chosen = selected || available[0]?.id || "";
      setWorkspaceId(chosen);
      if (!chosen) {
        setWorkforce({ units: [], members: [], capabilities: [], positions: [] });
        return;
      }
      const [result, specialistResult, blueprintResult] = await Promise.all([
        api<Workforce>(`/v1/orgs/${orgId()}/workforce?workspace_id=${encodeURIComponent(chosen)}`),
        api<{ specialists: Specialist[] }>(`/v1/orgs/${orgId()}/workforce/specialists?workspace_id=${encodeURIComponent(chosen)}`),
        api<{ blueprints: TeamBlueprint[] }>(`/v1/orgs/${orgId()}/workforce/blueprints?workspace_id=${encodeURIComponent(chosen)}`),
      ]);
      setWorkforce(result);
      setSpecialists(specialistResult.specialists);
      setBlueprints(blueprintResult.blueprints);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!orgId()) setError("Configure NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
    else void load("");
  }, []);

  async function bootstrap() {
    if (!workspaceId) return;
    setBootstrapping(true);
    setError("");
    try {
      await api(`/v1/orgs/${orgId()}/workforce/bootstrap?workspace_id=${encodeURIComponent(workspaceId)}`, {
        method: "POST",
      });
      await load(workspaceId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBootstrapping(false);
    }
  }

  const groups = useMemo(() => {
    const groupUnits = workforce.units.filter((unit) => unit.unit_type === "group");
    return GROUP_ORDER.map((name) => {
      const group = groupUnits.find((unit) => unit.name === name);
      const departments = workforce.units.filter(
        (unit) => unit.unit_type === "department" && unit.parent_unit_id === group?.id,
      );
      return { name, group, departments };
    });
  }, [workforce.units]);

  const counts = {
    groups: workforce.units.filter((u) => u.unit_type === "group").length,
    departments: workforce.units.filter((u) => u.unit_type === "department").length,
    teams: workforce.units.filter((u) => u.unit_type === "team").length,
    positions: workforce.positions.length,
    members: workforce.members.length,
    active: workforce.members.filter((m) => m.status === "active").length,
  };

  return (
    <Page
      eyebrow="ORGANIZATION & PEOPLE"
      title="Agency workforce"
      description="Your reporting structure, autonomous role records and authority boundaries. Founder authority remains separate from every agent and organization role."
    >
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace chart</div>
          <span className="panel-note">{loading ? "Loading…" : `${counts.members} workforce records`}</span>
        </div>
        <div className="toolbar">
          <select className="field" value={workspaceId} onChange={(e) => void load(e.target.value)}>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
            ))}
          </select>
          <button className="button" onClick={() => void load(workspaceId)} disabled={!workspaceId || loading}>Refresh</button>
          <button className="button" onClick={() => void bootstrap()} disabled={!workspaceId || bootstrapping}>
            {bootstrapping ? "Provisioning…" : "Provision 16 departments"}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        <div className="grid stats" style={{ marginTop: 16 }}>
          <div className="panel"><div className="panel-note">Functional groups</div><div className="stat-value">{counts.groups}/5</div></div>
          <div className="panel"><div className="panel-note">Departments</div><div className="stat-value">{counts.departments}/16</div></div>
          <div className="panel"><div className="panel-note">Teams</div><div className="stat-value">{counts.teams}</div></div>
          <div className="panel"><div className="panel-note">Defined positions</div><div className="stat-value">{counts.positions}</div></div>
          <div className="panel"><div className="panel-note">Active members</div><div className="stat-value">{counts.active}/{counts.members}</div></div>
        </div>
        {!workforce.units.length && !loading && (
          <div className="empty">
            <strong>No workforce chart provisioned</strong>
            Use the founder-authorized provisioning action to create the five groups and all sixteen departments. This does not activate any agent.
          </div>
        )}
      </section>

      <div style={{ height: 16 }} />
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Specialist registry</div>
          <span className="panel-note">{specialists.length} Claude-owned profile references · not executable in the OS</span>
        </div>
        <div className="grid dashboard-grid">
          {specialists.map((specialist) => (
            <div className="activity-row" key={specialist.specialist_key}>
              <span className="activity-dot" />
              <div style={{ minWidth: 0 }}>
                <div className="activity-title">{specialist.title}</div>
                <div className="activity-meta">{specialist.department_key} · {specialist.specialist_key}</div>
                <div className="activity-meta">Runtime owner: Claude · {specialist.status}</div>
                <div className="activity-meta">Profile source: {specialist.profile_ref}</div>
                <div className="activity-meta">No OS-side prompt execution or automatic tool grants</div>
              </div>
            </div>
          ))}
        </div>
      </section>
      <div style={{ height: 16 }} />
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Team blueprints</div>
          <span className="panel-note">{blueprints.length} versioned playbooks · preview only</span>
        </div>
        {blueprints.map((blueprint) => (
          <div className="activity-row" key={blueprint.slug}>
            <span className="activity-dot" />
            <div style={{ minWidth: 0, width: "100%" }}>
              <div className="activity-title">{blueprint.title}</div>
              <div className="activity-meta">{blueprint.summary}</div>
              {blueprint.groups.map((group) => (
                <div key={group.group} style={{ marginTop: 8 }}>
                  <div className="activity-meta"><strong>{group.group}</strong> · {group.activation}</div>
                  {group.tasks.map((task) => (
                    <div className="activity-meta" key={task.title}>
                      {task.title} — {task.specialist_key} · review required
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <div style={{ height: 16 }} />
      <div className="grid dashboard-grid">
        {groups.map(({ name, group, departments }) => (
          <section className="panel" key={name}>
            <div className="panel-head">
              <div className="panel-title">{name}</div>
              <span className="panel-note">{departments.length} departments</span>
            </div>
            {group && departments.length ? departments.map((department) => {
              const members = workforce.members.filter((member) =>
                member.department_key === department.department_key ||
                member.department_key === `${department.department_key}_head`,
              );
              return (
                <div className="activity-row" key={department.id}>
                  <span className="activity-dot" />
                  <div style={{ minWidth: 0 }}>
                    <div className="activity-title">{department.name}</div>
                    <div className="activity-meta">{department.description}</div>
                    <div className="activity-meta">
                      {members.map((member) => `${member.title} · ${member.status}`).join("  |  ") || "No member record"}
                    </div>
                  </div>
                </div>
              );
            }) : <div className="empty">Not provisioned yet.</div>}
          </section>
        ))}
      </div>

      <div style={{ height: 16 }} />
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Member registry</div>
          <span className="panel-note">{workforce.members.length} records · {workforce.capabilities.filter((c) => c.enabled).length} enabled capability grants</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Member</th><th>Department / role</th><th>Reports to</th><th>Type</th><th>Autonomy</th><th>Status</th></tr></thead>
            <tbody>
              {workforce.members.map((member) => {
                const manager = workforce.members.find((candidate) => candidate.id === member.manager_member_id);
                return (
                  <tr key={member.id}>
                    <td>{member.name}{member.is_founder_reserved ? <div className="activity-meta">Founder-reserved authority</div> : null}</td>
                    <td>{member.title}<div className="activity-meta">{member.department_key}</div></td>
                    <td>{manager?.name || (member.is_founder_reserved ? "Supreme authority" : "Unassigned")}</td>
                    <td>{member.member_type}</td>
                    <td>L{member.autonomy_level}</td>
                    <td><span className="status">{member.status}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!workforce.members.length && <div className="empty">Workforce members will appear after provisioning.</div>}
        </div>
      </section>
      <div style={{ height: 16 }} />
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Position & team catalogue</div>
          <span className="panel-note">{workforce.positions.length} defined positions</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Position</th><th>Department / group</th><th>Team</th><th>Reports to</th><th>Autonomy ceiling</th><th>Occupancy</th></tr></thead>
            <tbody>
              {workforce.positions.map((position) => {
                const assigned = workforce.members.find((member) => member.id === position.assigned_member_id);
                const team = workforce.units.find((unit) => unit.id === position.team_unit_id);
                const manager = workforce.positions.find((candidate) => candidate.position_key === position.reports_to_position_key);
                return (
                  <tr key={position.id}>
                    <td>{position.title}<div className="activity-meta">{position.position_key}</div></td>
                    <td>{position.department_key}</td>
                    <td>{team?.name || position.group_key}</td>
                    <td>{manager?.title || "Founder / executive authority"}</td>
                    <td>L{position.autonomy_ceiling}</td>
                    <td>{assigned ? assigned.status : "Unassigned position"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!workforce.positions.length && <div className="empty">Position catalogue will be provisioned with the workforce chart.</div>}
        </div>
      </section>
      <div style={{ height: 16 }} />
      <div className="notice">
        Provisioning creates organisational records only. Claude sessions, autonomous tool access, external communications and protected actions remain disabled until separately configured, tested and approved.
      </div>
    </Page>
  );
}
