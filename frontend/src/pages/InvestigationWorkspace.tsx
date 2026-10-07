import React, { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, type BackendClaim, type BackendImage } from '../api';
import {
  AlertTriangle, CheckCircle, Clock, Minus, ArrowRight, ArrowLeft,
  Eye, MapPin, Hash, Thermometer, Map, Zap, User, Shield, RefreshCw,
  ChevronDown, ChevronRight, Info, XCircle,
} from 'lucide-react';

// ─── Tiny shared helpers ──────────────────────────────────────────────────────

function Pill({ text, variant }: { text: string; variant: 'supports' | 'contradicts' | 'inconclusive' | 'missing' | 'neutral' | 'info' }) {
  const styles: Record<string, { bg: string; color: string }> = {
    supports: { bg: '#f0fdf4', color: '#16a34a' },
    contradicts: { bg: '#fef2f2', color: '#dc2626' },
    inconclusive: { bg: '#fefce8', color: '#854d0e' },
    missing: { bg: '#f8fafc', color: '#64748b' },
    neutral: { bg: '#f1f5f9', color: '#475569' },
    info: { bg: '#eff6ff', color: '#1d4ed8' },
  };
  const s = styles[variant] || styles.neutral;
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: s.bg, color: s.color }}>
      {text}
    </span>
  );
}

function Section({ title, icon, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, marginBottom: 12, overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '13px 16px',
          border: 'none', background: open ? '#f8fafc' : 'white', cursor: 'pointer',
          borderBottom: open ? '1px solid #e2e8f0' : 'none', textAlign: 'left',
        }}
      >
        {icon}
        <span style={{ fontSize: 13, fontWeight: 600, color: '#0d1117', flex: 1 }}>{title}</span>
        {open ? <ChevronDown size={14} color="#94a3b8" /> : <ChevronRight size={14} color="#94a3b8" />}
      </button>
      {open && <div style={{ padding: '14px 16px' }}>{children}</div>}
    </div>
  );
}

function EciBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color = pct >= 70 ? '#16a34a' : pct >= 40 ? '#ca8a04' : '#dc2626';
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 32, fontWeight: 800, color }}>{value.toFixed(1)}</span>
        <span style={{ fontSize: 14, color: '#94a3b8' }}>/ 100</span>
        <span style={{ fontSize: 12, color: '#94a3b8', marginLeft: 4 }}>Evidence Consistency Index</span>
      </div>
      <div style={{ height: 8, background: '#f1f5f9', borderRadius: 4, overflow: 'hidden', maxWidth: 300 }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, transition: 'width 0.6s ease', borderRadius: 4 }} />
      </div>
      <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 6, maxWidth: 420 }}>
        Accumulated consistent evidence score — NOT a fraud probability.
        Each check earns points proportional to its weight and evidence quality.
      </p>
    </div>
  );
}

function FindingRow({ f }: { f: any }) {
  const vv = (v: string): 'supports' | 'contradicts' | 'inconclusive' | 'missing' => {
    if (v === 'supports') return 'supports';
    if (v === 'contradicts') return 'contradicts';
    if (v === 'inconclusive') return 'inconclusive';
    return 'missing';
  };
  return (
    <div style={{
      padding: '10px 12px', borderRadius: 6, border: '1px solid',
      borderColor: f.verdict === 'contradicts' ? '#fecaca' : f.verdict === 'supports' ? '#bbf7d0' : '#e2e8f0',
      background: f.verdict === 'contradicts' ? '#fff5f5' : f.verdict === 'supports' ? '#f0fdf4' : 'white',
      marginBottom: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Pill text={f.verdict} variant={vv(f.verdict)} />
        {f.severity && <Pill text={f.severity} variant={f.severity === 'high' ? 'contradicts' : 'inconclusive'} />}
        {!f.independent && <Pill text="AI-dependent" variant="neutral" />}
        <span style={{ fontSize: 12, fontWeight: 600, color: '#374151', flex: 1 }}>{f.title}</span>
        <span style={{ fontSize: 11, color: '#94a3b8' }}>weight {f.weight.toFixed(2)}</span>
      </div>
      <div style={{ fontSize: 12, color: '#475569' }}>{f.detail}</div>
      {f.limitations?.length > 0 && (
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
          ⚠ {f.limitations.join(' · ')}
        </div>
      )}
      {f.evidence_ids?.length > 0 && (
        <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 3, fontFamily: 'DM Mono, monospace' }}>
          Evidence: {f.evidence_ids.join(', ')}
        </div>
      )}
    </div>
  );
}

function EvidenceItem({ e }: { e: any }) {
  const isAvail = e.status === 'available';
  return (
    <div style={{
      padding: '8px 12px', borderRadius: 6, border: '1px solid #f1f5f9',
      background: isAvail ? 'white' : '#fafafa', marginBottom: 6,
      opacity: isAvail ? 1 : 0.65,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
        {isAvail ? <CheckCircle size={11} color="#16a34a" /> : <XCircle size={11} color="#94a3b8" />}
        <span style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}>{e.description || e.evidence_type}</span>
        <span style={{ fontSize: 10, color: '#94a3b8', marginLeft: 'auto', fontFamily: 'DM Mono, monospace' }}>
          {e.evidence_id}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 10 }}>
        <span style={{ color: '#7c3aed' }}>
          source: <strong>{e.provenance || e.evidence_type}</strong>
        </span>
        {e.quality_score != null && (
          <span style={{ color: '#64748b' }}>quality: {(e.quality_score * 100).toFixed(0)}%</span>
        )}
        {e.status !== 'available' && e.status && (
          <span style={{ color: '#ea580c' }}>status: {e.status}</span>
        )}
      </div>
    </div>
  );
}

function ModelRow({ m }: { m: any }) {
  const isNova = m.model_id?.includes('nova') || m.model_key?.includes('nova');
  const isMinistral = m.model_key?.includes('ministral');
  const isTitan = m.model_key?.includes('titan');
  const typeLabel = isTitan ? 'Embedding' : isNova && m.task?.includes('photo') ? 'Vision (image pixels)' : 'Text reasoning only';
  return (
    <div style={{
      padding: '10px 12px', borderRadius: 6, border: '1px solid',
      borderColor: m.ok ? '#bbf7d0' : '#fecaca',
      background: m.ok ? '#f0fdf4' : '#fef2f2', marginBottom: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {m.ok ? <CheckCircle size={13} color="#16a34a" /> : <XCircle size={13} color="#dc2626" />}
        <span style={{ fontSize: 12, fontWeight: 700, color: '#0d1117', fontFamily: 'DM Mono, monospace' }}>
          {m.model_id || m.model_key}
        </span>
        <Pill text={typeLabel} variant="info" />
        <span style={{ fontSize: 11, color: '#64748b' }}>{m.task}</span>
        {m.fallback_of && <Pill text={`fallback of ${m.fallback_of}`} variant="inconclusive" />}
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 6, flexWrap: 'wrap', fontSize: 11, color: '#64748b' }}>
        {m.latency_ms != null && <span>⏱ {m.latency_ms} ms</span>}
        {m.input_tokens != null && <span>↑ {m.input_tokens} tokens in</span>}
        {m.output_tokens != null && <span>↓ {m.output_tokens} tokens out</span>}
        {m.cost_estimate_usd != null && <span>💰 ${m.cost_estimate_usd.toFixed(6)}</span>}
        {m.confidence && <span>confidence: {m.confidence}</span>}
        {m.error && <span style={{ color: '#dc2626' }}>error: {m.error}</span>}
      </div>
      {isMinistral && (
        <div style={{ fontSize: 10, color: '#7c3aed', marginTop: 4 }}>
          ℹ Ministral reviewed Nova Lite's TEXT observations — it did NOT see image pixels directly.
        </div>
      )}
    </div>
  );
}

function ToolRow({ t }: { t: any }) {
  const statusVariant = t.status === 'success' ? 'supports' : t.status === 'failed' ? 'contradicts' : 'inconclusive';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderBottom: '1px solid #f1f5f9', fontSize: 12 }}>
      <Pill text={t.status} variant={statusVariant} />
      <span style={{ fontWeight: 600, color: '#374151' }}>{t.tool}</span>
      <span style={{ color: '#94a3b8' }}>{t.source_name || t.source_type}</span>
      {t.latency_ms != null && <span style={{ color: '#94a3b8', marginLeft: 'auto' }}>{t.latency_ms} ms</span>}
      {t.error && <span style={{ color: '#dc2626', fontSize: 11 }}>{t.error}</span>}
    </div>
  );
}

function DecisionPanel({ claimId, queueStatus, onDecided }: {
  claimId: string; queueStatus?: string; onDecided: () => void;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decided, setDecided] = useState(false);

  async function decide(decision: string) {
    setBusy(true);
    setError(null);
    try {
      await api.decide(claimId, decision, note || undefined);
      setDecided(true);
      setTimeout(onDecided, 1000);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  if (decided) {
    return (
      <div style={{ padding: '12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6 }}>
        <CheckCircle size={14} color="#16a34a" style={{ display: 'inline', marginRight: 6 }} />
        <span style={{ fontSize: 13, color: '#16a34a', fontWeight: 600 }}>Decision recorded. Reloading…</span>
      </div>
    );
  }

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
        padding: '8px 12px', background: '#fff7ed', border: '1px solid #fed7aa',
        borderRadius: 6,
      }}>
        <User size={13} color="#ea580c" />
        <span style={{ fontSize: 12, color: '#9a3412', fontWeight: 600 }}>
          HUMAN REVIEWER ACTION REQUIRED — The AI has flagged this for your judgment
        </span>
      </div>

      <div style={{ fontSize: 12, color: '#475569', marginBottom: 8 }}>
        The AI verification result above is decision support only, not a final determination.
        As the authorised reviewer, your decision is the binding record.
      </div>

      {error && (
        <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 8, padding: '6px 10px', background: '#fef2f2', borderRadius: 4 }}>
          {error}
        </div>
      )}

      <textarea
        value={note}
        onChange={e => setNote(e.target.value)}
        placeholder="Reviewer note (optional) — your reasoning will be recorded in the audit trail"
        rows={2}
        style={{
          width: '100%', padding: '8px 10px', fontSize: 12, border: '1px solid #d1d5db',
          borderRadius: 6, fontFamily: 'inherit', resize: 'vertical', marginBottom: 10,
          boxSizing: 'border-box',
        }}
      />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => decide('approve_for_processing')}
          disabled={busy}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 600, borderRadius: 6, border: 'none',
            background: '#156235', color: 'white', cursor: 'pointer',
          }}
        >
          ✓ Approve for Processing
        </button>
        <button
          onClick={() => decide('reject')}
          disabled={busy}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 600, borderRadius: 6, border: 'none',
            background: '#dc2626', color: 'white', cursor: 'pointer',
          }}
        >
          ✗ Reject
        </button>
        <button
          onClick={() => decide('request_more_information')}
          disabled={busy}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 600, borderRadius: 6,
            border: '1px solid #d1d5db', background: 'white', color: '#374151', cursor: 'pointer',
          }}
        >
          ? Request More Information
        </button>
      </div>
    </div>
  );
}

// ─── Main InvestigationWorkspace ─────────────────────────────────────────────

export function InvestigationWorkspace() {
  const { claimId } = useParams<{ claimId: string }>();
  const [claim, setClaim] = useState<BackendClaim | null>(null);
  const [agResult, setAgResult] = useState<any | null>(null);
  const [mvpReport, setMvpReport] = useState<any | null>(null);
  const [queue, setQueue] = useState<any | null>(null);
  const [loadingClaim, setLoadingClaim] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!claimId) return;
    setLoadingClaim(true);
    setError(null);
    try {
      const c = await api.getClaim(claimId);
      setClaim(c);
      // Try to get existing agentic or MVP report
      try {
        const r = await api.getReport(claimId);
        setMvpReport(r);
      } catch { /* no report yet */ }
      // Check review queue
      try {
        const q = await api.reviewQueue('open');
        const item = q.items.find(i => i.claim_id === claimId);
        setQueue(item || null);
      } catch { /* ignore */ }
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setLoadingClaim(false);
    }
  }, [claimId]);

  useEffect(() => { load(); }, [load]);

  async function startInvestigation() {
    if (!claimId) return;
    setInvestigating(true);
    setError(null);
    setAgResult(null);
    try {
      const result = await api.verifyAgentic(claimId);
      setAgResult(result);
      // Refresh claim and queue status
      await load();
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setInvestigating(false);
    }
  }

  if (loadingClaim) {
    return (
      <div style={{ textAlign: 'center', padding: 60, color: '#94a3b8' }}>
        <RefreshCw size={20} style={{ marginBottom: 8 }} />
        <div>Loading claim…</div>
      </div>
    );
  }

  if (error && !claim) {
    return (
      <div style={{ maxWidth: 600, margin: '40px auto', padding: '16px', background: '#fef2f2', borderRadius: 8, border: '1px solid #fecaca' }}>
        <AlertTriangle size={16} color="#dc2626" style={{ display: 'inline', marginRight: 8 }} />
        <span style={{ color: '#dc2626', fontSize: 14 }}>{error}</span>
        <div style={{ marginTop: 12 }}>
          <Link to="/" style={{ color: '#156235', fontSize: 13 }}>← Back to Dashboard</Link>
        </div>
      </div>
    );
  }

  if (!claim) return null;

  const report = agResult?.report || null;
  const auditReport = agResult?.audit_report || null;
  const state = agResult?.state || null;

  // Determine verification status from agentic or MVP report
  const activeReport = report || mvpReport;
  const status = activeReport?.status;
  const statusVariant = status?.includes('Support') ? 'supports' : status?.includes('Contradict') ? 'contradicts' : status?.includes('Partial') ? 'inconclusive' : 'missing';

  // Human review info
  const routing = activeReport?.routing;
  const humanRequired = routing?.human_review_required;

  // From review queue
  const queueDecided = queue === null && mvpReport; // if queue item gone, might be decided

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 20 }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#64748b', textDecoration: 'none', marginTop: 4, flexShrink: 0 }}>
          <ArrowLeft size={13} /> Dashboard
        </Link>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 18, fontWeight: 700, color: '#0d1117', margin: 0 }}>
              Investigation Workspace
            </h1>
            <code style={{ fontSize: 13, color: '#156235', fontFamily: 'DM Mono, monospace', background: '#f0fdf4', padding: '2px 8px', borderRadius: 4 }}>
              {claimId}
            </code>
            {status && <Pill text={status} variant={statusVariant} />}
          </div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
            Claimant-submitted data · not verified until investigation runs
          </div>
        </div>
        {!report && (
          <button
            onClick={startInvestigation}
            disabled={investigating}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '9px 18px',
              fontSize: 13, fontWeight: 600, borderRadius: 6, border: 'none',
              background: investigating ? '#94a3b8' : '#156235', color: 'white',
              cursor: investigating ? 'wait' : 'pointer', flexShrink: 0,
            }}
          >
            {investigating ? <><RefreshCw size={13} /> Investigating…</> : <><Zap size={13} /> Start Investigation</>}
          </button>
        )}
        {report && (
          <button
            onClick={startInvestigation}
            disabled={investigating}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px',
              fontSize: 12, borderRadius: 6, border: '1px solid #e2e8f0',
              background: 'white', color: '#475569', cursor: 'pointer',
            }}
          >
            <RefreshCw size={12} /> Re-investigate
          </button>
        )}
      </div>

      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '12px 16px', marginBottom: 16, fontSize: 13, color: '#dc2626' }}>
          <AlertTriangle size={14} style={{ display: 'inline', marginRight: 6 }} />
          {error}
        </div>
      )}

      {investigating && (
        <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '16px', marginBottom: 16, textAlign: 'center' }}>
          <RefreshCw size={16} color="#1d4ed8" style={{ marginBottom: 8 }} />
          <div style={{ fontSize: 13, color: '#1d4ed8', fontWeight: 600 }}>Running agentic investigation…</div>
          <div style={{ fontSize: 12, color: '#3b82f6', marginTop: 4 }}>
            Planner → Model routing → Nova Lite vision → Independent review → Weather → Geo → Deterministic verification → ECI
          </div>
        </div>
      )}

      {/* Claim panel */}
      <Section title="Claim" icon={<FileText size={14} color="#475569" />}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px 16px', fontSize: 13, marginBottom: 8 }}>
          <div><span style={{ color: '#94a3b8' }}>Cause: </span><strong>{claim.claim.claimed_cause}</strong></div>
          <div><span style={{ color: '#94a3b8' }}>Survey: </span><strong>{claim.claim.survey_no}</strong></div>
          <div><span style={{ color: '#94a3b8' }}>Incident: </span><strong>{claim.claim.incident_date}</strong></div>
          {claim.claim.claimed_crop && <div><span style={{ color: '#94a3b8' }}>Crop: </span>{claim.claim.claimed_crop}</div>}
          {claim.claim.claimed_stage && <div><span style={{ color: '#94a3b8' }}>Stage: </span>{claim.claim.claimed_stage.replace(/_/g, ' ')}</div>}
          {claim.claim.village_lgd && <div><span style={{ color: '#94a3b8' }}>LGD: </span>{claim.claim.village_lgd}</div>}
          {claim.claim.claimed_lat && <div><span style={{ color: '#94a3b8' }}>Lat: </span>{claim.claim.claimed_lat}</div>}
          {claim.claim.claimed_lon && <div><span style={{ color: '#94a3b8' }}>Lon: </span>{claim.claim.claimed_lon}</div>}
          {claim.claim.farmer_name && <div><span style={{ color: '#94a3b8' }}>Name: </span>{claim.claim.farmer_name}</div>}
        </div>
        {claim.claim.description && (
          <div style={{ fontSize: 12, color: '#64748b', fontStyle: 'italic', marginBottom: 8 }}>
            Claimant statement: "{claim.claim.description}"
          </div>
        )}
        <div style={{ fontSize: 11, color: '#94a3b8' }}>
          Provenance: Submitted by claimant · unverified
        </div>
      </Section>

      {/* Evidence photos */}
      <Section title={`Evidence Photos (${claim.images.length})`} icon={<Eye size={14} color="#475569" />}>
        {claim.images.length === 0 ? (
          <div style={{ fontSize: 13, color: '#94a3b8', fontStyle: 'italic' }}>
            No photos attached. Investigation will rely on reference data, weather, and geo evidence only.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            {claim.images.map((img) => <PhotoCard key={img.image_key} img={img} claimId={claimId!} />)}
          </div>
        )}
      </Section>

      {/* No report yet */}
      {!activeReport && !investigating && (
        <div style={{
          background: 'white', border: '1px dashed #d1d5db', borderRadius: 8, padding: '32px',
          textAlign: 'center', color: '#94a3b8',
        }}>
          <Zap size={24} style={{ marginBottom: 8 }} />
          <div style={{ fontSize: 14, fontWeight: 600 }}>No investigation run yet</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>Click "Start Investigation" to run the full agentic pipeline.</div>
        </div>
      )}

      {/* Agentic result sections */}
      {activeReport && (
        <>
          {/* Status + ECI */}
          <Section title="Verification Result" icon={<Shield size={14} color="#475569" />}>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
                  AI INVESTIGATION RESULT — Not a human approval
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#0d1117', marginBottom: 4 }}>{status}</div>
                <div style={{ fontSize: 12, color: '#475569' }}>{activeReport.status_reason}</div>
              </div>
              {activeReport.scores?.evidence_consistency_index != null && (
                <div style={{ flex: 1, minWidth: 260 }}>
                  <EciBar value={activeReport.scores.evidence_consistency_index} />
                </div>
              )}
            </div>

            {/* Scores breakdown */}
            {activeReport.scores?.breakdown?.length > 0 && (
              <details style={{ marginTop: 12 }}>
                <summary style={{ fontSize: 12, color: '#64748b', cursor: 'pointer' }}>ECI breakdown per check</summary>
                <table style={{ width: '100%', marginTop: 8, borderCollapse: 'collapse', fontSize: 11 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                      {['check', 'verdict', 'weight', 'max pts', 'earned', 'evidence quality'].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '4px 8px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {activeReport.scores.breakdown.map((b: any, i: number) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                        <td style={{ padding: '4px 8px', fontFamily: 'DM Mono, monospace', color: '#374151' }}>{b.check_id}</td>
                        <td style={{ padding: '4px 8px' }}><Pill text={b.verdict} variant={b.verdict === 'supports' ? 'supports' : b.verdict === 'contradicts' ? 'contradicts' : b.verdict === 'inconclusive' ? 'inconclusive' : 'missing'} /></td>
                        <td style={{ padding: '4px 8px', color: '#64748b' }}>{b.weight?.toFixed(2)}</td>
                        <td style={{ padding: '4px 8px', color: '#64748b' }}>{b.max_points?.toFixed(1)}</td>
                        <td style={{ padding: '4px 8px', fontWeight: 600, color: b.points_earned > 0 ? '#16a34a' : '#94a3b8' }}>{b.points_earned?.toFixed(1)}</td>
                        <td style={{ padding: '4px 8px', color: '#64748b' }}>{b.evidence_quality?.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </Section>

          {/* Findings */}
          <Section title="Findings" icon={<CheckCircle size={14} color="#475569" />}>
            {(activeReport.findings || []).map((f: any, i: number) => <FindingRow key={i} f={f} />)}
          </Section>

          {/* Contradictions */}
          {activeReport.contradictions?.length > 0 && (
            <Section title={`Contradictions (${activeReport.contradictions.length})`} icon={<AlertTriangle size={14} color="#dc2626" />} defaultOpen={true}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {activeReport.contradictions.map((c: string, i: number) => (
                  <div key={i} style={{ padding: '10px 12px', background: '#fff5f5', border: '1px solid #fecaca', borderRadius: 6, fontSize: 12, color: '#991b1b' }}>
                    <AlertTriangle size={12} style={{ display: 'inline', marginRight: 6 }} />{c}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Missing evidence */}
          {activeReport.missing_evidence?.length > 0 && (
            <Section title="Missing Evidence" icon={<Minus size={14} color="#64748b" />} defaultOpen={false}>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {activeReport.missing_evidence.map((m: string, i: number) => (
                  <li key={i} style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{m}</li>
                ))}
              </ul>
            </Section>
          )}

          {/* Evidence items */}
          <Section title="Evidence Items" icon={<Map size={14} color="#475569" />} defaultOpen={false}>
            {(activeReport.evidence || []).map((e: any, i: number) => <EvidenceItem key={i} e={e} />)}
          </Section>

          {/* Independent review (from agentic state) */}
          {state?.independent_review && (
            <Section title="Independent Model Review" icon={<Eye size={14} color="#7c3aed" />}>
              <div style={{ fontSize: 11, color: '#7c3aed', marginBottom: 8, padding: '6px 10px', background: '#ede9fe', borderRadius: 4 }}>
                ℹ Ministral reviewed Nova Lite's TEXT observations only — it did NOT see image pixels.
              </div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>
                <strong>Stance: </strong>
                {state.independent_review.ok === false ? (
                  <span style={{ color: '#dc2626' }}>Review failed — {state.independent_review.error}</span>
                ) : state.independent_review.output?.agrees_with_claim === true ? (
                  <span style={{ color: '#16a34a' }}>Agrees with claim</span>
                ) : state.independent_review.output?.agrees_with_claim === false ? (
                  <span style={{ color: '#dc2626' }}>Does NOT agree with claim</span>
                ) : (
                  <span style={{ color: '#ca8a04' }}>Undecided / insufficient observations</span>
                )}
              </div>
              {state.independent_review.output?.reasoning && (
                <div style={{ fontSize: 12, color: '#475569', marginBottom: 4 }}>
                  Reasoning: {state.independent_review.output.reasoning}
                </div>
              )}
              {state.independent_review.output?.disagreement && (
                <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 4 }}>
                  Disagreement: {state.independent_review.output.disagreement}
                </div>
              )}
              <div style={{ fontSize: 11, color: '#94a3b8' }}>
                Model: {state.independent_review.model_key || '—'} · Confidence: {state.independent_review.output?.confidence || '—'}
                {state.independent_review.fallback_used && ' · fallback used'}
              </div>
            </Section>
          )}

          {/* Human Review */}
          <Section title="Human Review" icon={<User size={14} color={humanRequired ? '#dc2626' : '#64748b'} />}>
            {humanRequired ? (
              <>
                <div style={{ marginBottom: 12 }}>
                  <Pill text="Review Required" variant="contradicts" />
                  <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                    {routing.reasons?.map((r: string, i: number) => (
                      <li key={i} style={{ fontSize: 12, color: '#475569', marginBottom: 4 }}>{r}</li>
                    ))}
                  </ul>
                </div>
                <DecisionPanel claimId={claimId!} onDecided={load} />
              </>
            ) : (
              <div style={{ fontSize: 13, color: '#16a34a' }}>
                <CheckCircle size={13} style={{ display: 'inline', marginRight: 6 }} />
                Human review not required by the AI investigation. If you wish to review manually, use the API directly.
              </div>
            )}
          </Section>

          {/* Audit trail */}
          {auditReport && (
            <Section title="Audit Trail" icon={<Clock size={14} color="#475569" />} defaultOpen={false}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, fontSize: 12, marginBottom: 12 }}>
                <div>
                  <span style={{ color: '#94a3b8' }}>Investigation ID: </span>
                  <code style={{ fontFamily: 'DM Mono, monospace', fontSize: 11 }}>{auditReport.investigation_id}</code>
                </div>
                <div><span style={{ color: '#94a3b8' }}>Steps: </span>{auditReport.total_steps}</div>
                <div><span style={{ color: '#94a3b8' }}>Duration: </span>{activeReport.total_latency_ms ? `${activeReport.total_latency_ms} ms` : '—'}</div>
                {auditReport.token_usage?.total_input_tokens != null && (
                  <div><span style={{ color: '#94a3b8' }}>Tokens in: </span>{auditReport.token_usage.total_input_tokens}</div>
                )}
                {auditReport.token_usage?.total_output_tokens != null && (
                  <div><span style={{ color: '#94a3b8' }}>Tokens out: </span>{auditReport.token_usage.total_output_tokens}</div>
                )}
                {auditReport.token_usage?.total_cost_estimate_usd != null && (
                  <div><span style={{ color: '#94a3b8' }}>Cost: </span>${auditReport.token_usage.total_cost_estimate_usd.toFixed(6)}</div>
                )}
              </div>

              {auditReport.models_invoked?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Models Invoked</div>
                  {auditReport.models_invoked.map((m: any, i: number) => <ModelRow key={i} m={m} />)}
                </div>
              )}

              {auditReport.tools_invoked?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Tools Invoked</div>
                  {auditReport.tools_invoked.map((t: any, i: number) => <ToolRow key={i} t={t} />)}
                </div>
              )}

              {auditReport.routing_decisions?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Routing Decisions</div>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                        {['task', 'model', 'reason', 'fallback of'].map(h => (
                          <th key={h} style={{ textAlign: 'left', padding: '4px 8px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {auditReport.routing_decisions.map((rd: any, i: number) => (
                        <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                          <td style={{ padding: '4px 8px', fontFamily: 'DM Mono, monospace', fontSize: 10 }}>{rd.task}</td>
                          <td style={{ padding: '4px 8px', fontWeight: 600, color: '#374151' }}>{rd.model_key}</td>
                          <td style={{ padding: '4px 8px', color: '#64748b' }}>{rd.reason}</td>
                          <td style={{ padding: '4px 8px', color: '#94a3b8' }}>{rd.fallback_of || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <details>
                <summary style={{ fontSize: 11, color: '#94a3b8', cursor: 'pointer' }}>
                  Full step trace ({auditReport.steps?.length} steps)
                </summary>
                <div style={{ marginTop: 8, maxHeight: 400, overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                        {['#', 'step', 'agent', 'model/tool', 'status', 'ms', 'detail'].map(h => (
                          <th key={h} style={{ textAlign: 'left', padding: '3px 6px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {auditReport.steps?.map((s: any, i: number) => (
                        <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                          <td style={{ padding: '3px 6px', color: '#94a3b8' }}>{i + 1}</td>
                          <td style={{ padding: '3px 6px', fontFamily: 'DM Mono, monospace' }}>{s.step}</td>
                          <td style={{ padding: '3px 6px', color: '#64748b' }}>{s.agent}</td>
                          <td style={{ padding: '3px 6px', color: '#7c3aed' }}>{s.model || s.tool || '—'}</td>
                          <td style={{ padding: '3px 6px' }}>
                            <span style={{ color: s.status === 'success' ? '#16a34a' : s.status === 'failed' ? '#dc2626' : '#ca8a04' }}>
                              {s.status}
                            </span>
                          </td>
                          <td style={{ padding: '3px 6px', color: '#94a3b8' }}>{s.latency_ms ?? '—'}</td>
                          <td style={{ padding: '3px 6px', color: '#64748b', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {s.output_summary || s.error || s.routing_reason || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </Section>
          )}

          {/* Limitations */}
          {activeReport.limitations?.length > 0 && (
            <Section title="Limitations of this Report" icon={<Info size={14} color="#64748b" />} defaultOpen={false}>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {activeReport.limitations.map((l: string, i: number) => (
                  <li key={i} style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{l}</li>
                ))}
              </ul>
            </Section>
          )}
        </>
      )}

      {/* MVP report fallback if no agentic result */}
      {!agResult && mvpReport && !activeReport && (
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>
          MVP report found. Run Start Investigation to get full agentic analysis.
        </div>
      )}
    </div>
  );
}

// Missing import
import { FileText } from 'lucide-react';

function PhotoCard({ img, claimId }: { img: BackendImage; claimId: string }) {
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden', background: 'white' }}>
      {img.file_available ? (
        <img
          src={api.imageFileUrl(claimId, img.image_key)}
          alt={img.filename || 'evidence photo'}
          style={{ width: '100%', height: 140, objectFit: 'cover', display: 'block' }}
          onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
        />
      ) : (
        <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc', color: '#94a3b8', fontSize: 11 }}>
          File not on disk
        </div>
      )}
      <div style={{ padding: '8px 10px' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: img.source === 'dataset' ? '#7c3aed' : '#0369a1', marginBottom: 4 }}>
          {img.source === 'dataset' ? '● Dataset' : '● Uploaded'}
        </div>
        <div style={{ fontSize: 11, color: '#374151', marginBottom: 3 }}>{img.filename || '(unnamed)'}</div>
        {img.sha256 && (
          <div style={{ fontSize: 10, color: '#94a3b8', fontFamily: 'DM Mono, monospace' }}>
            SHA256: {img.sha256.slice(0, 12)}…
          </div>
        )}
        {img.width && <div style={{ fontSize: 10, color: '#94a3b8' }}>{img.width}×{img.height}px</div>}
        {img.exif?.gps_lat != null && (
          <div style={{ fontSize: 10, color: '#059669' }}>
            EXIF GPS: {img.exif.gps_lat.toFixed(4)}°N
          </div>
        )}
        {img.exif?.captured_at && (
          <div style={{ fontSize: 10, color: '#64748b' }}>EXIF: {img.exif.captured_at}</div>
        )}
        <div style={{ fontSize: 10, marginTop: 3 }}>
          {img.file_available ? (
            <span style={{ color: '#16a34a' }}>✓ File available</span>
          ) : (
            <span style={{ color: '#ea580c' }}>⚠ File missing</span>
          )}
        </div>
      </div>
    </div>
  );
}
