import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type BackendStats, type ReviewQueueItem, type BackendClaim } from '../api';
import { AlertTriangle, RefreshCw, CheckCircle, Clock, FileText, Activity } from 'lucide-react';

// ── Shared tiny UI helpers ────────────────────────────────────────────────

function KpiCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div style={{
      background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '16px 20px',
    }}>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#0d1117', lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', marginTop: 4 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const s = status?.toLowerCase() ?? '';
  let bg = '#f1f5f9', color = '#64748b', text = status;
  if (s.includes('support')) { bg = '#f0fdf4'; color = '#16a34a'; text = 'Supported'; }
  else if (s.includes('contradict')) { bg = '#fef2f2'; color = '#dc2626'; text = 'Contradicted'; }
  else if (s.includes('partial')) { bg = '#fefce8'; color = '#ca8a04'; text = 'Partial'; }
  else if (s.includes('insufficient')) { bg = '#fff7ed'; color = '#ea580c'; text = 'Insufficient'; }
  else if (s.includes('further')) { bg = '#f5f3ff'; color = '#7c3aed'; text = 'Needs Review'; }
  else if (s === 'submitted') { bg = '#f0f9ff'; color = '#0369a1'; text = 'Submitted'; }
  else if (s === 'reported') { bg = '#f0fdf4'; color = '#15803d'; text = 'Reported'; }
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: bg, color }}>
      {text}
    </span>
  );
}

function Err({ msg, onRetry }: { msg: string; onRetry?: () => void }) {
  return (
    <div style={{
      background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
      padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 10, color: '#dc2626',
    }}>
      <AlertTriangle size={16} />
      <span style={{ fontSize: 13, flex: 1 }}>{msg}</span>
      {onRetry && (
        <button onClick={onRetry} style={{ fontSize: 12, color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
          Retry
        </button>
      )}
    </div>
  );
}

// ── Dashboard ────────────────────────────────────────────────────────────

export function Dashboard() {
  const [stats, setStats] = useState<BackendStats | null>(null);
  const [queue, setQueue] = useState<ReviewQueueItem[] | null>(null);
  const [claims, setClaims] = useState<BackendClaim[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [s, q, c] = await Promise.all([
        api.stats(),
        api.reviewQueue('open'),
        api.listClaims(50),
      ]);
      setStats(s);
      setQueue(q.items);
      setClaims(c.items);
    } catch (err: any) {
      setError(err?.message || 'Failed to load dashboard data from backend.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: '#0d1117', margin: 0 }}>
            Investigation Dashboard
          </h1>
          <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
            All figures come from the ReliefTrace backend — nothing is simulated.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={load}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px',
              fontSize: 13, borderRadius: 6, border: '1px solid #e2e8f0',
              background: 'white', cursor: 'pointer', color: '#475569',
            }}
          >
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
            Refresh
          </button>
          <Link
            to="/submit"
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px',
              fontSize: 13, fontWeight: 600, borderRadius: 6, border: 'none',
              background: '#156235', color: 'white', textDecoration: 'none',
            }}
          >
            + Submit Claim
          </Link>
        </div>
      </div>

      {error && <Err msg={error} onRetry={load} />}

      {/* KPIs */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
          <KpiCard label="Claims Recorded" value={stats.claims} sub="Total submitted" />
          <KpiCard label="Verified" value={stats.reported} sub="Report generated" />
          <KpiCard label="Awaiting Review" value={stats.review_open} sub="Human review needed" />
          <KpiCard label="Live Nova Calls" value={stats.ai_calls} sub="Real Bedrock invocations" />
        </div>
      )}

      {loading && !stats && (
        <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 14 }}>
          Loading from backend…
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Review Queue */}
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8 }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={14} color="#dc2626" />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#0d1117' }}>Review Queue</span>
            {queue && (
              <span style={{
                fontSize: 11, fontWeight: 700, background: queue.length > 0 ? '#fef2f2' : '#f0f9ff',
                color: queue.length > 0 ? '#dc2626' : '#0369a1',
                padding: '1px 7px', borderRadius: 99, marginLeft: 'auto',
              }}>
                {queue.length} open
              </span>
            )}
          </div>
          <div style={{ padding: 0 }}>
            {queue == null && !error && (
              <div style={{ padding: '24px 16px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Loading…</div>
            )}
            {queue?.length === 0 && (
              <div style={{ padding: '24px 16px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                No claims awaiting human review.
              </div>
            )}
            {queue?.map((q) => (
              <Link
                key={q.claim_id}
                to={`/claims/${q.claim_id}`}
                style={{
                  display: 'block', padding: '12px 16px', borderBottom: '1px solid #f8fafc',
                  textDecoration: 'none', transition: 'background 0.1s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                  <code style={{ fontSize: 11, color: '#156235', fontFamily: 'DM Mono, monospace' }}>{q.claim_id}</code>
                  <StatusPill status={q.report_status || 'open'} />
                </div>
                <div style={{ fontSize: 12, color: '#475569' }}>
                  {q.claimed_cause} · Survey {q.survey_no}
                  {q.confidence != null && (
                    <span style={{ marginLeft: 8, color: '#94a3b8' }}>ECI: {q.confidence}</span>
                  )}
                </div>
                {q.reasons?.[0] && (
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 3 }}>
                    {q.reasons[0]}{q.reasons.length > 1 ? ` (+${q.reasons.length - 1} more)` : ''}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </div>

        {/* All Claims */}
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8 }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileText size={14} color="#475569" />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#0d1117' }}>All Claims</span>
            {claims && (
              <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 'auto' }}>
                {claims.length} records
              </span>
            )}
          </div>
          <div style={{ padding: 0 }}>
            {claims == null && !error && (
              <div style={{ padding: '24px 16px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Loading…</div>
            )}
            {claims?.length === 0 && (
              <div style={{ padding: '24px 16px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                No claims yet. <Link to="/submit" style={{ color: '#156235' }}>Submit one →</Link>
              </div>
            )}
            {claims?.map((c) => (
              <Link
                key={c.claim_id}
                to={`/claims/${c.claim_id}`}
                style={{
                  display: 'block', padding: '11px 16px', borderBottom: '1px solid #f8fafc',
                  textDecoration: 'none', transition: 'background 0.1s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                  <code style={{ fontSize: 11, color: '#156235', fontFamily: 'DM Mono, monospace' }}>{c.claim_id}</code>
                  <StatusPill status={c.status} />
                </div>
                <div style={{ fontSize: 12, color: '#475569' }}>
                  {c.claim.claimed_cause.replace('_', ' ')} · {c.claim.survey_no}
                  {c.claim.claimed_crop && ` · ${c.claim.claimed_crop}`}
                </div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                  {c.claim.incident_date} · {c.images.length} image{c.images.length !== 1 ? 's' : ''}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
