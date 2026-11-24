"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Page from "@/components/page";
import Notice from "@/components/notice";
import { api, orgId, type Workspace } from "@/lib/api";

type Contract = { id: string; contract_number: string; title: string; status: string; amount_minor: number; currency: string };
type Invoice = {
  id: string; workspace_id: string; client_id: string; contract_id: string; project_id: string | null;
  invoice_number: string; title: string; description: string; line_items: {description:string;amount_minor:number}[];
  amount_minor: number; paid_minor: number; outstanding_minor: number; currency: string; due_date: string;
  status: string; approval_id: string | null; external_reference: string; issued_at: string | null;
};
type Receipt = { id: string; invoice_id: string; external_reference: string; amount_minor: number; currency: string; payment_method: string; source: string; paid_at: string };
function money(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amount / 100);
}

export default function InvoicesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [receipts, setReceipts] = useState<Record<string,Receipt[]>>({});
  const [expandedReceipts, setExpandedReceipts] = useState<Record<string,boolean>>({});
  const [contractId, setContractId] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [issuedRefs, setIssuedRefs] = useState<Record<string,string>>({});
  const [issuedDates, setIssuedDates] = useState<Record<string,string>>({});
  const [paymentRefs, setPaymentRefs] = useState<Record<string,string>>({});
  const [paymentAmounts, setPaymentAmounts] = useState<Record<string,string>>({});
  const [paymentMethods, setPaymentMethods] = useState<Record<string,string>>({});
  const [paymentSources, setPaymentSources] = useState<Record<string,string>>({});
  const [paymentDates, setPaymentDates] = useState<Record<string,string>>({});
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

  const loadData = useCallback(async () => {
    if (!workspace || !orgId()) return;
    setLoading(true); setError("");
    try {
      const [contractRows, invoiceRows] = await Promise.all([
        api<Contract[]>(`/v1/orgs/${orgId()}/operations/contracts?workspace_id=${encodeURIComponent(workspace)}&status=executed`),
        api<Invoice[]>(`/v1/orgs/${orgId()}/operations/invoices?workspace_id=${encodeURIComponent(workspace)}`),
      ]);
      setContracts(contractRows);
      setInvoices(invoiceRows);
      setContractId(current => contractRows.some(item => item.id === current) ? current : contractRows[0]?.id || "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function createInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selected = contracts.find(item => item.id === contractId);
    const numericAmount = Number(amount);
    if (!selected || !workspace || !invoiceNumber.trim() || title.trim().length < 3 || !dueDate ||
        !Number.isFinite(numericAmount) || numericAmount <= 0) return;
    setSaving(true); setError("");
    try {
      await api<Invoice>(`/v1/orgs/${orgId()}/operations/invoices`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace, contract_id: contractId,
          invoice_number: invoiceNumber.trim(), title: title.trim(),
          description: description.trim(),
          line_items: [{ description: title.trim(), amount_minor: Math.round(numericAmount * 100) }],
          due_date: new Date(dueDate).toISOString(),
        }),
      });
      setInvoiceNumber(""); setTitle(""); setAmount(""); setDescription(""); setDueDate("");
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function submitInvoice(item: Invoice) {
    setBusyId(item.id); setError("");
    try {
      await api<Invoice>(`/v1/orgs/${orgId()}/operations/invoices/${item.id}/submit-for-approval`, { method: "POST" });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function recordIssued(item: Invoice) {
    const reference = (issuedRefs[item.id] || "").trim();
    const issuedAt = issuedDates[item.id];
    if (!item.approval_id || reference.length < 3 || !issuedAt) {
      setError("Enter the external invoice reference and issue timestamp.");
      return;
    }
    setBusyId(item.id); setError("");
    try {
      await api<Invoice>(`/v1/orgs/${orgId()}/operations/invoices/${item.id}/record-issued`, {
        method: "POST",
        body: JSON.stringify({ approval_id: item.approval_id, external_reference: reference, issued_at: new Date(issuedAt).toISOString() }),
      });
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function toggleReceipts(item: Invoice) {
    if (expandedReceipts[item.id]) {
      setExpandedReceipts(v => ({...v,[item.id]:false}));
      return;
    }
    setBusyId(item.id); setError("");
    try {
      const rows = await api<Receipt[]>(`/v1/orgs/${orgId()}/operations/invoices/${item.id}/payments`);
      setReceipts(v => ({...v,[item.id]:rows}));
      setExpandedReceipts(v => ({...v,[item.id]:true}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  async function recordPayment(item: Invoice) {
    const reference = (paymentRefs[item.id] || "").trim();
    const numericAmount = Number(paymentAmounts[item.id]);
    const paidAt = paymentDates[item.id];
    if (reference.length < 3 || !Number.isFinite(numericAmount) || numericAmount <= 0 || !paidAt || !(paymentSources[item.id] || "").trim()) {
      setError("Enter a unique payment reference, positive amount, source and payment date.");
      return;
    }
    setBusyId(item.id); setError("");
    try {
      await api<Receipt>(`/v1/orgs/${orgId()}/operations/invoices/${item.id}/payments`, {
        method: "POST",
        body: JSON.stringify({
          external_reference: reference,
          amount_minor: Math.round(numericAmount * 100),
          payment_method: paymentMethods[item.id] || "bank_transfer",
          source: paymentSources[item.id].trim(),
          paid_at: new Date(paidAt).toISOString(),
        }),
      });
      setPaymentRefs(v => ({...v,[item.id]:""}));
      setPaymentAmounts(v => ({...v,[item.id]:""}));
      await loadData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId("");
    }
  }

  return (
    <Page eyebrow="FINANCE & CONTROL" title="Invoices & receivables" description="Prepare invoice drafts against executed contracts, route issuance through Founder Authority and reconcile receipts against outstanding balances.">
      <Notice>The OS does not send invoices, create tax documents, collect payments or move money. Record an invoice as issued only after it has been issued through your external accounting process. Payment receipts are append-only reconciliation evidence; they do not initiate transactions. External accounting and payment integrations come later.</Notice>
      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Workspace</div>
          <select className="field" value={workspace} onChange={e => setWorkspace(e.target.value)} disabled={!workspaces.length}>
            {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <h2 className="panel-title">Create invoice draft</h2>
        <form onSubmit={createInvoice} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10,marginBottom:22}}>
          <select className="field" value={contractId} onChange={e => setContractId(e.target.value)} required>
            <option value="">Select executed contract</option>
            {contracts.map(item => <option key={item.id} value={item.id}>{item.contract_number} · {item.title} · {money(item.amount_minor,item.currency)}</option>)}
          </select>
          <input className="field" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} placeholder="Invoice number" maxLength={80} required />
          <input className="field" value={title} onChange={e => setTitle(e.target.value)} placeholder="Milestone / invoice title" maxLength={240} minLength={3} required />
          <input className="field" type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder={`Amount (${contracts.find(item => item.id === contractId)?.currency || "currency"})`} min={0.01} step="0.01" required />
          <input className="field" type="datetime-local" value={dueDate} onChange={e => setDueDate(e.target.value)} required />
          <input className="field" value={description} onChange={e => setDescription(e.target.value)} placeholder="Description / billing notes" maxLength={8000} />
          <button className="button primary" type="submit" disabled={saving || !contractId}>{saving ? "Saving…" : "Save invoice draft"}</button>
        </form>
        <div className="panel-head">
          <div className="panel-title">Invoice register <span className="activity-meta">({invoices.length})</span></div>
          <button className="button secondary" type="button" onClick={() => void loadData()}>Refresh</button>
        </div>
        {loading ? <div className="empty">Loading invoices…</div> : invoices.length ? (
          <div className="activity">
            {invoices.map(item => (
              <div className="activity-row" key={item.id} style={{alignItems:"flex-start"}}>
                <span className="activity-dot" />
                <div style={{minWidth:0,width:"100%"}}>
                  <div className="activity-title">{item.title}</div>
                  <div className="activity-meta">{item.invoice_number} · {item.status.replace("_"," ")} · Due {new Date(item.due_date).toLocaleDateString()}</div>
                  <div className="activity-meta">Total {money(item.amount_minor,item.currency)} · Received {money(item.paid_minor,item.currency)} · Outstanding {money(item.outstanding_minor,item.currency)}</div>
                  {item.external_reference && <div className="activity-meta">Issued reference: {item.external_reference}</div>}
                  {item.status === "draft" || item.status === "rejected" ? <button className="button secondary" type="button" onClick={() => void submitInvoice(item)} disabled={busyId===item.id}>{busyId===item.id ? "Submitting…" : "Request Founder invoice issuance approval"}</button> : null}
                  {item.status === "pending_approval" && <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:8,marginTop:10}}>
                    <input className="field" value={issuedRefs[item.id] || ""} onChange={e => setIssuedRefs(v => ({...v,[item.id]:e.target.value}))} placeholder="External invoice reference" maxLength={240} />
                    <input className="field" type="datetime-local" value={issuedDates[item.id] || ""} onChange={e => setIssuedDates(v => ({...v,[item.id]:e.target.value}))} />
                    <button className="button primary" type="button" onClick={() => void recordIssued(item)} disabled={busyId===item.id}>{busyId===item.id ? "Recording…" : "Record external issuance"}</button>
                    <Link href="/approvals" className="activity-meta">Review invoice issuance in Founder Approvals</Link>
                  </div>}
                  {(item.status === "issued" || item.status === "partially_paid") && <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))",gap:8,marginTop:12}}>
                    <input className="field" value={paymentRefs[item.id] || ""} onChange={e => setPaymentRefs(v => ({...v,[item.id]:e.target.value}))} placeholder="Bank / provider transaction reference" maxLength={240} />
                    <input className="field" type="number" value={paymentAmounts[item.id] || ""} onChange={e => setPaymentAmounts(v => ({...v,[item.id]:e.target.value}))} placeholder={`Receipt amount (${item.currency})`} min={0.01} step="0.01" />
                    <select className="field" value={paymentMethods[item.id] || "bank_transfer"} onChange={e => setPaymentMethods(v => ({...v,[item.id]:e.target.value}))}>
                      <option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option><option value="card">Card</option><option value="cheque">Cheque</option><option value="cash">Cash</option><option value="other">Other</option>
                    </select>
                    <input className="field" value={paymentSources[item.id] || ""} onChange={e => setPaymentSources(v => ({...v,[item.id]:e.target.value}))} placeholder="Reconciliation source" maxLength={80} />
                    <input className="field" type="datetime-local" value={paymentDates[item.id] || ""} onChange={e => setPaymentDates(v => ({...v,[item.id]:e.target.value}))} />
                    <button className="button primary" type="button" onClick={() => void recordPayment(item)} disabled={busyId===item.id}>{busyId===item.id ? "Reconciling…" : "Record receipt"}</button>
                  </div>}
                  {item.status === "paid" && <div className="activity-meta">Invoice fully reconciled.</div>}
                  {(item.status === "issued" || item.status === "partially_paid" || item.status === "paid") && <div style={{marginTop:8}}>
                    <button className="button secondary" type="button" onClick={() => void toggleReceipts(item)} disabled={busyId===item.id}>{busyId===item.id ? "Loading…" : expandedReceipts[item.id] ? "Hide receipt history" : "View receipt history"}</button>
                    {expandedReceipts[item.id] && <div className="activity-meta" style={{marginTop:8}}>
                      {(receipts[item.id] || []).length ? (receipts[item.id] || []).map(receipt => <div key={receipt.id}>{money(receipt.amount_minor,receipt.currency)} · {receipt.payment_method} · {receipt.external_reference} · {new Date(receipt.paid_at).toLocaleString()}</div>) : "No payment receipts recorded."}
                    </div>}
                  </div>}
                  {item.approval_id && <div className="activity-meta">Approval ID: {item.approval_id}</div>}
                </div>
              </div>
            ))}
          </div>
        ) : <div className="empty"><strong>No invoices yet</strong>Invoices can be drafted only against executed contracts. They remain internal until a founder approves issuance and the external issue reference is recorded.</div>}
      </section>
    </Page>
  );
}
