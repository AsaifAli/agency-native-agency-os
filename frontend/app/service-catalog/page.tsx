"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Offering = {
  id: string;
  workspace_id: string;
  code: string;
  name: string;
  service_line: string;
  description: string;
  pricing_model: string;
  indicative_price_minor: number | null;
  currency: string;
  typical_duration_days: number;
  target_outcomes: string[];
  deliverables: string[];
  required_inputs: string[];
  exclusions: string[];
  notes: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
};
function lines(value: string) { return value.split("\n").map(item => item.trim()).filter(Boolean); }
function money(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amount / 100);
}

export default function ServiceCataloguePage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [serviceLine, setServiceLine] = useState("");
  const [description, setDescription] = useState("");
  const [pricingModel, setPricingModel] = useState("custom");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [duration, setDuration] = useState("0");
  const [outcomes, setOutcomes] = useState("");
  const [deliverables, setDeliverables] = useState("");
  const [inputs, setInputs] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState("");

  useEffect(() => {
    async function loadWorkspaces() {
      try {
        if (!orgId()) throw new Error("Set NEXT_PUBLIC_ORG_ID in frontend/.env.local.");
        const rows = await api<Workspace[]>(`/v1/orgs/${orgId()}/workspaces`);
        setWorkspaces(rows);
        if (rows[0]) setWorkspace(rows[0].id);
        else setLoading(false);
      } catch (e) {
        setError((e as Error).message);
        setLoading(false);
      }
    }
    void loadWorkspaces();
  }, []);

  const loadOfferings = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true);
    setError("");
    try {
      const rows = await api<Offering[]>(
        `/v1/orgs/${orgId()}/operations/service-catalog?workspace_id=${encodeURIComponent(workspace)}`
      );
      setOfferings(rows);
    } catch (e) {
      setError((e as Error).message);
      setOfferings([]);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadOfferings(); }, [loadOfferings]);

  async function createOffering(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || code.trim().length < 2 || name.trim().length < 2) return;
    const numericPrice = Number(price);
    if (pricingModel === "fixed" && (!price || !Number.isFinite(numericPrice) || numericPrice < 0)) {
      setError("Fixed-price offerings require an indicative price.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api<Offering>(`/v1/orgs/${orgId()}/operations/service-catalog`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace,
          code: code.trim().toLowerCase(),
          name: name.trim(),
          service_line: serviceLine.trim(),
          description: description.trim(),
          pricing_model: pricingModel,
          indicative_price_minor: price.trim() ? Math.round(numericPrice * 100) : null,
          currency,
          typical_duration_days: Number(duration) || 0,
          target_outcomes: lines(outcomes),
          deliverables: lines(deliverables),
          required_inputs: lines(inputs),
          exclusions: lines(exclusions),
          notes: notes.trim(),
        }),
      });
      setCode(""); setName(""); setServiceLine(""); setDescription(""); setPrice(""); setDuration("0");
      setOutcomes(""); setDeliverables(""); setInputs(""); setExclusions(""); setNotes("");
      await loadOfferings();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(item: Offering, status: "active" | "retired") {
    setBusyId(item.id);
    setError("");
    try {
      await api<Offering>(`/v1/orgs/${orgId()}/operations/service-catalog/${item.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await loadOfferings();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  return (
    <Page eyebrow="REVENUE & DELIVERY" title="Service catalogue" description="Define what the agency offers, expected outcomes, deliverables, inputs, exclusions and indicative commercial models. Founder approval controls activation.">
      <Notice>Catalogue entries are internal service definitions, not customer offers or binding prices. Fixed fees are indicative; custom, hourly and retainer work must be scoped and approved through a proposal. Activating an offering requires Founder Authority.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Create service offering draft</h2>
        <form onSubmit={createOffering} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:10,marginBottom:22}}>
          <input className="field" value={code} onChange={e => setCode(e.target.value)} placeholder="Unique code (e.g. ai-workflow)" maxLength={60} required />
          <input className="field" value={name} onChange={e => setName(e.target.value)} placeholder="Offering name" maxLength={200} required />
          <input className="field" value={serviceLine} onChange={e => setServiceLine(e.target.value)} placeholder="Service line" maxLength={120} required />
          <select className="field" value={pricingModel} onChange={e => setPricingModel(e.target.value)}>
            <option value="custom">Custom / scoped</option><option value="fixed">Fixed indicative fee</option><option value="hourly">Hourly</option><option value="retainer">Retainer</option>
          </select>
          <input className="field" type="number" value={price} onChange={e => setPrice(e.target.value)} placeholder={pricingModel === "fixed" ? "Required indicative fee" : "Indicative fee (optional)"} min={0} step="0.01" />
          <select className="field" value={currency} onChange={e => setCurrency(e.target.value)}>
            <option value="INR">INR</option><option value="USD">USD</option><option value="AED">AED</option><option value="SAR">SAR</option><option value="GBP">GBP</option>
          </select>
          <input className="field" type="number" value={duration} onChange={e => setDuration(e.target.value)} placeholder="Typical duration (days)" min={0} max={3650} />
          <textarea className="field" value={description} onChange={e => setDescription(e.target.value)} placeholder="Description and client problem addressed" maxLength={8000} minLength={10} rows={3} style={{gridColumn:"1 / -1"}} required />
          <textarea className="field" value={outcomes} onChange={e => setOutcomes(e.target.value)} placeholder="Target outcomes (one per line)" maxLength={5000} rows={3} />
          <textarea className="field" value={deliverables} onChange={e => setDeliverables(e.target.value)} placeholder="Deliverables (one per line)" maxLength={6000} rows={3} />
          <textarea className="field" value={inputs} onChange={e => setInputs(e.target.value)} placeholder="Required client inputs (one per line)" maxLength={6000} rows={3} />
          <textarea className="field" value={exclusions} onChange={e => setExclusions(e.target.value)} placeholder="Exclusions (one per line)" maxLength={6000} rows={3} />
          <textarea className="field" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Internal notes" maxLength={8000} rows={2} style={{gridColumn:"1 / -1"}} />
          <button className="button primary" type="submit" disabled={saving || !workspace}>{saving ? "Saving…" : "Save draft offering"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Service offerings <span className="activity-meta">({offerings.length})</span></div>
          <button className="button secondary" type="button" onClick={() => void loadOfferings()}>Refresh</button>
        </div>
        {loading ? <div className="empty">Loading service catalogue…</div> : offerings.length ? (
          <div className="activity">
            {offerings.map(item => (
              <div className="activity-row" key={item.id} style={{alignItems:"flex-start"}}>
                <span className="activity-dot" />
                <div style={{minWidth:0,width:"100%"}}>
                  <div className="activity-title">{item.name}</div>
                  <div className="activity-meta">{item.code} · {item.service_line} · {item.pricing_model} · {item.indicative_price_minor === null ? "Quote-based" : money(item.indicative_price_minor,item.currency)} · {item.status} · v{item.version}</div>
                  <p className="activity-meta">{item.description}</p>
                  {item.deliverables.length>0 && <div className="activity-meta">Deliverables: {item.deliverables.join(" · ")}</div>}
                  {item.exclusions.length>0 && <div className="activity-meta">Exclusions: {item.exclusions.join(" · ")}</div>}
                  {item.status === "draft" && <button className="button primary" type="button" onClick={() => void changeStatus(item,"active")} disabled={busyId===item.id}>{busyId===item.id ? "Saving…" : "Activate (Founder Authority)"}</button>}
                  {item.status === "active" && <button className="button secondary" type="button" onClick={() => void changeStatus(item,"retired")} disabled={busyId===item.id}>{busyId===item.id ? "Saving…" : "Retire offering"}</button>}
                </div>
              </div>
            ))}
          </div>
        ) : <div className="empty"><strong>No service offerings yet</strong>Define the agency&apos;s service lines and delivery boundaries before using them in client proposals.</div>}
      </section>
    </Page>
  );
}
