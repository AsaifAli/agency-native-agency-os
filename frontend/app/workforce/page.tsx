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
type Workforce = { units: Unit[]; members: Member[]; capabilities: Capability[] };

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
  const [workforce, setWorkforce] = useState<Workforce>({ units: [], members: [], capabilities: [] });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);

  async function load(selected = workspaceId) {
    setLoading(true);
    setError("");
    try {
      const available = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
      setWorkspaces(available);
      const chosen = selected || available[0]?.id || "";
      setWorkspaceId(chosen);
      if (!chosen) {
        setWorkforce({ units: [], members: [], capabilities: [] });
        return;
      }
      const result = await api<Workforce>(
        `/v1/orgs/${orgId()}/workforce?workspace_id=${encodeURIComponent(chosen)}`,
      );
      setWorkforce(result);
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
      <div className="notice">
        Provisioning creates organisational records only. Claude sessions, autonomous tool access, external communications and protected actions remain disabled until separately configured, tested and approved.
      </div>
    </Page>
  );
}
