"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type DraftStatus = "pending_review" | "approved" | "rejected" | "promoted";
type ResearchDraft = {
  id: string;
  company_name: string;
  summary: string;
  source_references: string[];
  fit_score: number;
  confidence_score: number;
  buying_signals: string[];
  risks: string[];
  status: DraftStatus;
  machine_identity_id: string;
  created_at: string;
  reviewed_at: string | null;
  promoted_lead_id: string | null;
};

const statusOptions: { value: DraftStatus; label: string }[] = [
  { value: "pending_review", label: "Pending review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "promoted", label: "Promoted to CRM" },
];

export default function ResearchDraftsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [status, setStatus] = useState<DraftStatus>("pending_review");
  const [drafts, setDrafts] = useState<ResearchDraft[]>([]);
  const [draftsKey, setDraftsKey] = useState("");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [pendingActionIds, setPendingActionIds] = useState<Set<string>>(() => new Set());
  const requestGeneration = useRef(0);
  const viewKey = `${orgId()}:${workspaceId}:${status}`;
  const viewKeyRef = useRef(viewKey);
  viewKeyRef.current = viewKey;
  const visibleDrafts = draftsKey === viewKey ? drafts : [];
  const viewLoading = loading || (!!workspaceId && draftsKey !== viewKey);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    async function loadWorkspaces() {
      try {
        if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
        setWorkspaces(rows);
        if (rows[0]) setWorkspaceId(rows[0].id);
        else setLoading(false);
      } catch (err) {
        setError((err as Error).message);
        setLoading(false);
      }
    }
    void loadWorkspaces();
  }, []);

  const loadDrafts = useCallback(async () => {
    const requestKey = `${orgId()}:${workspaceId}:${status}`;
    if (!workspaceId || !orgId() || viewKeyRef.current !== requestKey) return;
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError("");
    try {
      const result = await api<{ items: ResearchDraft[] }>(
        `/v1/orgs/${orgId()}/workspaces/${encodeURIComponent(workspaceId)}/lead-research-drafts?status=${status}&limit=100`,
      );
      if (requestGeneration.current === generation && viewKeyRef.current === requestKey) {
        setDrafts(result.items);
        setDraftsKey(requestKey);
      }
    } catch (err) {
      if (requestGeneration.current === generation && viewKeyRef.current === requestKey) {
        setError((err as Error).message);
      }
    } finally {
      if (requestGeneration.current === generation && viewKeyRef.current === requestKey) {
        setLoading(false);
      }
    }
  }, [workspaceId, status]);

  useEffect(() => {
    void loadDrafts();
    return () => {
      requestGeneration.current += 1;
    };
  }, [loadDrafts]);

  async function reviewDraft(draft: ResearchDraft, decision: "approve" | "reject") {
    if (pendingActionIds.has(draft.id)) return;
    setPendingActionIds((current) => new Set(current).add(draft.id));
    setError("");
    setNotice("");
    try {
      await api(
        `/v1/orgs/${orgId()}/workspaces/${encodeURIComponent(workspaceId)}/lead-research-drafts/${draft.id}/review`,
        {
          method: "POST",
          body: JSON.stringify({
            decision,
            review_note: reviewNotes[draft.id] || "",
          }),
        },
      );
      setNotice(decision === "approve" ? "Research approved. CRM promotion is still a separate action." : "Research rejected.");
      await loadDrafts();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPendingActionIds((current) => {
        const next = new Set(current);
        next.delete(draft.id);
        return next;
      });
    }
  }

  async function promoteDraft(draft: ResearchDraft) {
    if (pendingActionIds.has(draft.id)) return;
    setPendingActionIds((current) => new Set(current).add(draft.id));
    setError("");
    setNotice("");
    try {
      const result = await api<{ lead_id: string; replayed: boolean }>(
        `/v1/orgs/${orgId()}/workspaces/${encodeURIComponent(workspaceId)}/lead-research-drafts/${draft.id}/promote`,
        { method: "POST" },
      );
      setNotice(`Promoted to CRM lead ${result.lead_id}.`);
      await loadDrafts();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPendingActionIds((current) => {
        const next = new Set(current);
        next.delete(draft.id);
        return next;
      });
    }
  }

  return (
    <Page
      eyebrow="REVENUE ENGINE · FOUNDER REVIEW"
      title="Agent research review"
      description="Review public-source company research captured by Revenue agents before it enters your CRM."
    >
      <Notice>
        Agents can submit public research drafts, but cannot approve or promote them. Source URLs are supplied by the agent and are not independently verified by this screen. No contact details or outreach messages are created here.
      </Notice>

      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Review queue</div>
          <label htmlFor="research-workspace-filter" className="activity-meta">Workspace</label>
          <select id="research-workspace-filter" aria-label="Workspace filter" className="field" value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
            ))}
          </select>
          <label htmlFor="research-status-filter" className="activity-meta">Draft status</label>
          <select id="research-status-filter" aria-label="Draft status filter" className="field" value={status} onChange={(event) => setStatus(event.target.value as DraftStatus)}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <button className="button secondary" type="button" onClick={() => void loadDrafts()} disabled={loading || !workspaceId}>
            Refresh
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {notice && <div className="success">{notice}</div>}
        {viewLoading ? (
          <div className="empty">Loading research drafts…</div>
        ) : visibleDrafts.length === 0 ? (
          <div className="empty">No {status.replaceAll("_", " ")} drafts in this workspace.</div>
        ) : (
          <div className="activity">
            {visibleDrafts.map((draft) => (
              <article className="panel" key={draft.id} style={{ marginBottom: 14 }}>
                <div className="panel-head">
                  <div>
                    <div className="panel-title">{draft.company_name}</div>
                    <div className="activity-meta">
                      Fit {draft.fit_score}/100 · Confidence {draft.confidence_score}/100 · Captured {new Date(draft.created_at).toLocaleString()}
                    </div>
                  </div>
                  <span className={`status ${draft.status}`}>{draft.status.replaceAll("_", " ")}</span>
                </div>
                <p style={{ lineHeight: 1.65, whiteSpace: "pre-wrap" }}>{draft.summary}</p>
                <div className="two-col">
                  <div>
                    <div className="panel-note">BUYING SIGNALS</div>
                    {draft.buying_signals.length ? <ul>{draft.buying_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul> : <p className="activity-meta">None supplied</p>}
                  </div>
                  <div>
                    <div className="panel-note">RISKS & UNKNOWNS</div>
                    {draft.risks.length ? <ul>{draft.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul> : <p className="activity-meta">None supplied</p>}
                  </div>
                </div>
                <div style={{ marginTop: 12 }}>
                  <div className="panel-note">SOURCE REFERENCES</div>
                  <ul>
                    {draft.source_references.map((source) => (
                      <li key={source}>
                        <a href={source} target="_blank" rel="noreferrer" className="activity-meta">{source}</a>
                      </li>
                    ))}
                  </ul>
                </div>
                {draft.status === "pending_review" && (
                  <div style={{ display: "grid", gap: 10, marginTop: 16 }}>
                    <textarea
                      className="field"
                      rows={2}
                      maxLength={2000}
                      placeholder="Optional founder review note"
                      value={reviewNotes[draft.id] || ""}
                      onChange={(event) => setReviewNotes((current) => ({ ...current, [draft.id]: event.target.value }))}
                    />
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button className="button primary" type="button" disabled={pendingActionIds.has(draft.id)} onClick={() => void reviewDraft(draft, "approve")}>
                        {pendingActionIds.has(draft.id) ? "Saving…" : "Approve for CRM"}
                      </button>
                      <button className="button secondary" type="button" disabled={pendingActionIds.has(draft.id)} onClick={() => void reviewDraft(draft, "reject")}>
                        Reject
                      </button>
                    </div>
                  </div>
                )}
                {draft.status === "approved" && (
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
                    <button className="button primary" type="button" disabled={pendingActionIds.has(draft.id)} onClick={() => void promoteDraft(draft)}>
                      {pendingActionIds.has(draft.id) ? "Promoting…" : "Promote to CRM"}
                    </button>
                    <span className="activity-meta">This creates a CRM lead and research record. It does not create a contact or send outreach.</span>
                  </div>
                )}
                {draft.status === "promoted" && draft.promoted_lead_id && (
                  <p className="activity-meta" style={{ marginTop: 14 }}>CRM lead ID: {draft.promoted_lead_id}</p>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </Page>
  );
}
