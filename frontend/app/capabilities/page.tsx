"use client";

import { useEffect, useMemo, useState } from "react";
import Page from "@/components/page";
import { api, orgId } from "@/lib/api";

type SkillSource = {
  id: string;
  repository: string;
  revision: string;
  license: string;
  use: string;
};

type SkillSummary = {
  name: string;
  description: string;
  category: string;
  sources: SkillSource[];
  recommended_departments: string[];
  review_status: string;
  enabled: boolean;
  allowed_data_classes: string[];
  allowed_tools: string[];
  content_sha256: string;
};

type SkillDetail = SkillSummary & { content: string };

export default function Capabilities() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [selected, setSelected] = useState<SkillDetail | null>(null);
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      if (!orgId()) {
        setError("Configure NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        setLoading(false);
        return;
      }
      try {
        const result = await api<{ skills: SkillSummary[] }>(
          `/v1/orgs/${orgId()}/skills`,
        );
        setSkills(result.skills);
        if (result.skills.length) {
          const first = await api<SkillDetail>(
            `/v1/orgs/${orgId()}/skills/${encodeURIComponent(result.skills[0].name)}`,
          );
          setSelected(first);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  async function openSkill(name: string) {
    setDetailLoading(true);
    setError("");
    try {
      const result = await api<SkillDetail>(
        `/v1/orgs/${orgId()}/skills/${encodeURIComponent(name)}`,
      );
      setSelected(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }

  const categories = useMemo(
    () => ["all", ...Array.from(new Set(skills.map((skill) => skill.category))).sort()],
    [skills],
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skills.filter((skill) => {
      const categoryMatch = category === "all" || skill.category === category;
      const queryMatch = !needle || `${skill.name} ${skill.description} ${skill.category}`.toLowerCase().includes(needle);
      return categoryMatch && queryMatch;
    });
  }, [skills, category, query]);

  return (
    <Page
      eyebrow="AGENT CAPABILITIES"
      title="Skills library"
      description="Curated, version-pinned operating skills for planning, engineering, research, runtime governance and quality. Skills are separate from agent identities, tools and permissions."
    >
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Reviewed skill catalog</div>
          <span className="panel-note">{loading ? "Loading…" : `${skills.length} skills · read only`}</span>
        </div>
        <div className="toolbar">
          <input
            className="field"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search skills"
            aria-label="Search skills"
          />
          <select
            className="field"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            aria-label="Filter by category"
          >
            {categories.map((value) => (
              <option key={value} value={value}>{value === "all" ? "All categories" : value}</option>
            ))}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        {loading ? <div className="empty">Loading curated skills…</div> : null}
        {!loading && !error && !filtered.length ? <div className="empty">No skills match this filter.</div> : null}
        <div className="grid dashboard-grid" style={{ marginTop: 16 }}>
          {filtered.map((skill) => (
            <div
              className="panel"
              role="button"
              tabIndex={0}
              key={skill.name}
              onClick={() => void openSkill(skill.name)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void openSkill(skill.name);
                }
              }}
              aria-pressed={selected?.name === skill.name}
              style={{
                textAlign: "left",
                cursor: "pointer",
                borderColor: selected?.name === skill.name ? "var(--accent, #7c8cff)" : undefined,
              }}
            >
              <div className="panel-head">
                <div className="panel-title">{skill.name}</div>
                <span className="status">Reviewed</span>
              </div>
              <div className="activity-meta">{skill.category}</div>
              <p className="page-desc">{skill.description}</p>
              <div className="activity-meta">
                {skill.sources.map((source) => source.id).join(" · ")}
              </div>
              <div className="activity-meta">Disabled · no tool grants</div>
            </div>
          ))}
        </div>
      </section>

      <div style={{ height: 16 }} />
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">{selected?.name || "Skill detail"}</div>
          <span className="panel-note">{detailLoading ? "Loading…" : selected ? "Instruction preview" : "Select a skill"}</span>
        </div>
        {selected ? (
          <>
            <p className="page-desc">{selected.description}</p>
            <div className="activity-meta">
              Recommended departments: {selected.recommended_departments.join(", ") || "Not specified"}
            </div>
            <div className="activity-meta">
              Data classes: {selected.allowed_data_classes.join(", ")} · Tools: none · Runtime activation: disabled
            </div>
            <div className="activity-meta" style={{ overflowWrap: "anywhere" }}>
              SHA-256: {selected.content_sha256}
            </div>
            <div className="activity-meta">
              Sources: {selected.sources.map((source) => (
                <span key={source.id}>
                  <a href={source.repository} target="_blank" rel="noreferrer">{source.id}</a>
                  {" "}({source.revision.slice(0, 12)} · {source.license})
                  {" · "}
                </span>
              ))}
            </div>
            <pre style={{
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
              maxHeight: 560,
              overflow: "auto",
              padding: 16,
              borderRadius: 10,
              background: "var(--surface-muted, #101522)",
              fontSize: 13,
              lineHeight: 1.6,
            }}>{selected.content}</pre>
          </>
        ) : <div className="empty">Choose a skill to inspect its instructions, source revisions and content digest.</div>}
      </section>
      <div style={{ height: 16 }} />
      <div className="notice">
        Skills are reviewed instructions, not permission grants. All entries remain disabled, tool-free and restricted to public/synthetic data. They are not yet assigned to workforce members or injected into live provider sessions.
      </div>
    </Page>
  );
}
