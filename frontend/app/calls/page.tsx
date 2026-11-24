"use client";
import { useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import { api, orgId } from "@/lib/api";

type CallRecord = {
  id: string; workspace_id: string; lead_id: string | null; direction: string;
  status: string; phone_number: string; purpose: string; outcome: string;
  summary: string; recording_consent: string; duration_seconds: number | null;
  created_at: string;
};

export default function CallsPage() {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const org = orgId();
  const workspace = process.env.NEXT_PUBLIC_WORKSPACE_ID || "";
  const load = useCallback(async () => {
    if (!org || !workspace) { setError("Set NEXT_PUBLIC_ORG_ID and NEXT_PUBLIC_WORKSPACE_ID in the frontend environment to load call records."); setLoading(false); return; }
    try { setCalls(await api<CallRecord[]>(`/v1/orgs/${org}/telephony/calls?workspace_id=${encodeURIComponent(workspace)}`)); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load call records"); }
    finally { setLoading(false); }
  }, [org, workspace]);
  useEffect(() => { void load(); }, [load]);
  return <Page eyebrow="REVENUE OPERATIONS" title="Calls & transcripts" description="Workspace-scoped call history and conversation records. Telephony provider execution is not yet configured.">
    <div className="panel">
      <div className="panel-head"><div className="panel-title">Call history</div><button className="button secondary" onClick={() => { setLoading(true); void load(); }}>Refresh</button></div>
      {error && <div className="notice">{error}</div>}
      {loading ? <div className="empty">Loading call records…</div> : calls.length === 0 ? <div className="empty"><strong>No calls recorded yet</strong>Call records can be created through the authenticated telephony API. Provider connection and live calling are separate setup steps.</div> :
        <div style={{display:"grid",gap:10}}>{calls.map(call => <div key={call.id} className="panel" style={{padding:14}}>
          <div style={{display:"flex",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}><strong>{call.direction.toUpperCase()} · {call.phone_number}</strong><span className={`status ${call.status}`}>{call.status}</span></div>
          <div className="muted" style={{fontSize:12,marginTop:6}}>{call.purpose || "No purpose supplied"} · {new Date(call.created_at).toLocaleString()}</div>
          {call.summary && <p style={{marginTop:8}}>{call.summary}</p>}
          <div className="muted" style={{fontSize:11}}>Lead: {call.lead_id || "Not linked"} · Outcome: {call.outcome || "Pending"} · Recording consent: {call.recording_consent}</div>
        </div>)}</div>}
      <div className="notice" style={{marginTop:14}}>This page does not place or answer calls. Do not upload real client transcripts until retention, access and redaction policies are configured.</div>
    </div>
  </Page>;
}
