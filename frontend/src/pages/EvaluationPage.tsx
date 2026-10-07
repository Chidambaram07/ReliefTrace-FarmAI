import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { AlertTriangle, CheckCircle, XCircle, FlaskConical, Zap } from 'lucide-react';

function Pill({ text, variant }: { text: string; variant: 'supports' | 'contradicts' | 'inconclusive' | 'neutral' }) {
  const map = {
    supports: { bg: '#f0fdf4', color: '#16a34a' },
    contradicts: { bg: '#fef2f2', color: '#dc2626' },
    inconclusive: { bg: '#fefce8', color: '#854d0e' },
    neutral: { bg: '#f1f5f9', color: '#475569' },
  };
  const s = map[variant];
  return <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: s.bg, color: s.color }}>{text}</span>;
}

function ModelTable({ models }: { models: any[] }) {
  if (!models?.length) return null;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, marginTop: 6 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
          {['task', 'model', 'ok', 'tokens in/out', 'ms', 'cost'].map(h => (
            <th key={h} style={{ textAlign: 'left', padding: '3px 8px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {models.map((m, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
            <td style={{ padding: '3px 8px', fontFamily: 'DM Mono, monospace' }}>{m.task}</td>
            <td style={{ padding: '3px 8px', fontWeight: 600 }}>{m.model_id || m.model_key}</td>
            <td style={{ padding: '3px 8px' }}>
              {m.ok ? <CheckCircle size={11} color="#16a34a" /> : <XCircle size={11} color="#dc2626" />}
            </td>
            <td style={{ padding: '3px 8px', color: '#64748b' }}>{m.input_tokens ?? '—'}/{m.output_tokens ?? '—'}</td>
            <td style={{ padding: '3px 8px', color: '#64748b' }}>{m.latency_ms ?? '—'}</td>
            <td style={{ padding: '3px 8px', color: '#64748b' }}>{m.cost_estimate_usd != null ? `$${m.cost_estimate_usd.toFixed(6)}` : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ToolTable({ tools }: { tools: any[] }) {
  if (!tools?.length) return null;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, marginTop: 6 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
          {['tool', 'status', 'source', 'ms', 'error'].map(h => (
            <th key={h} style={{ textAlign: 'left', padding: '3px 8px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {tools.map((t, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
            <td style={{ padding: '3px 8px', fontFamily: 'DM Mono, monospace' }}>{t.tool}</td>
            <td style={{ padding: '3px 8px' }}>
              <Pill text={t.status} variant={t.status === 'success' ? 'supports' : t.status === 'failed' ? 'contradicts' : 'inconclusive'} />
            </td>
            <td style={{ padding: '3px 8px', color: '#64748b' }}>{t.source_name || t.source_type}</td>
            <td style={{ padding: '3px 8px', color: '#64748b' }}>{t.latency_ms ?? '—'}</td>
            <td style={{ padding: '3px 8px', color: '#dc2626', fontSize: 10 }}>{t.error || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ResultPanel({ result }: { result: any }) {
  if (!result) return null;
  const report = result.report;
  const auditReport = result.audit_report;
  const status = report?.status;
  const statusVariant = status?.includes('Support') ? 'supports' : status?.includes('Contradict') ? 'contradicts' : 'inconclusive';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
      {result.scenario && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 14px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#0d1117' }}>{result.scenario.name}</div>
          <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{result.scenario.description}</div>
          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2, fontFamily: 'DM Mono, monospace' }}>Claim: {result.claim_id}</div>
        </div>
      )}

      {result.intent && (
        <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '12px 14px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#1d4ed8', marginBottom: 4 }}>Intent Classification (deterministic, no model call)</div>
          <div style={{ fontSize: 12, color: '#1e40af' }}>{result.intent.label} ({result.intent.key})</div>
          <div style={{ fontSize: 11, color: '#3b82f6' }}>{result.intent.reason}</div>
        </div>
      )}

      {report && (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#0d1117' }}>Verification Result</div>
            <Pill text={status} variant={statusVariant} />
          </div>
          <div style={{ fontSize: 12, color: '#475569', marginBottom: 10 }}>{report.status_reason}</div>

          {report.scores && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 10 }}>
              {[
                { label: 'ECI', value: report.scores.evidence_consistency_index },
                { label: 'Coverage', value: report.scores.coverage },
                { label: 'Agreement', value: report.scores.agreement },
                { label: 'Evidence Quality', value: report.scores.evidence_quality },
              ].map(({ label, value }) => (
                <div key={label} style={{ background: '#f8fafc', borderRadius: 6, padding: '8px 10px', textAlign: 'center' }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#0d1117' }}>{value?.toFixed ? value.toFixed(1) : value}</div>
                  <div style={{ fontSize: 10, color: '#94a3b8' }}>{label}</div>
                </div>
              ))}
            </div>
          )}

          {report.contradictions?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#dc2626', marginBottom: 4 }}>Contradictions</div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {report.contradictions.map((c: string, i: number) => (
                  <li key={i} style={{ fontSize: 11, color: '#991b1b', marginBottom: 2 }}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {report.routing && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Pill text={report.routing.human_review_required ? 'Human Review Required' : 'No Review Required'} variant={report.routing.human_review_required ? 'contradicts' : 'supports'} />
              {report.routing.reasons?.length > 0 && (
                <span style={{ fontSize: 11, color: '#64748b' }}>{report.routing.reasons[0]}{report.routing.reasons.length > 1 ? ` (+${report.routing.reasons.length - 1})` : ''}</span>
              )}
            </div>
          )}
        </div>
      )}

      {result.contradictions != null && (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Contradictions Found</div>
          {result.contradictions.length === 0 ? (
            <div style={{ fontSize: 12, color: '#16a34a' }}>No contradictions found in the existing report.</div>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {result.contradictions.map((c: string, i: number) => (
                <li key={i} style={{ fontSize: 12, color: '#991b1b', marginBottom: 3 }}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {result.missing_evidence != null && (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Evidence Sufficiency</div>
          <div style={{ fontSize: 12, color: '#475569', marginBottom: 4 }}>
            Coverage: {result.coverage ?? 'N/A'} · ECI: {result.evidence_consistency_index ?? 'N/A'}
          </div>
          {result.missing_evidence.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {result.missing_evidence.map((m: string, i: number) => (
                <li key={i} style={{ fontSize: 12, color: '#64748b', marginBottom: 2 }}>{m}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {auditReport && (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#0d1117', marginBottom: 10 }}>Execution Trace</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, fontSize: 12, marginBottom: 10 }}>
            <div><span style={{ color: '#94a3b8' }}>Investigation ID: </span>
              <code style={{ fontFamily: 'DM Mono, monospace', fontSize: 10 }}>{auditReport.investigation_id}</code>
            </div>
            <div><span style={{ color: '#94a3b8' }}>Total steps: </span>{auditReport.total_steps}</div>
            {auditReport.token_usage?.total_input_tokens != null && (
              <div><span style={{ color: '#94a3b8' }}>Tokens: </span>{auditReport.token_usage.total_input_tokens} in / {auditReport.token_usage.total_output_tokens} out</div>
            )}
          </div>
          {auditReport.models_invoked?.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Models Invoked</div>
              <ModelTable models={auditReport.models_invoked} />
            </div>
          )}
          {auditReport.tools_invoked?.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Tools Invoked</div>
              <ToolTable tools={auditReport.tools_invoked} />
            </div>
          )}
          <details>
            <summary style={{ fontSize: 11, color: '#94a3b8', cursor: 'pointer' }}>Full step trace ({auditReport.steps?.length} steps)</summary>
            <div style={{ maxHeight: 300, overflowY: 'auto', marginTop: 6 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                <thead>
                  <tr>
                    {['step', 'agent', 'model/tool', 'status', 'ms', 'detail'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '3px 6px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {auditReport.steps?.map((s: any, i: number) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                      <td style={{ padding: '3px 6px', fontFamily: 'DM Mono, monospace' }}>{s.step}</td>
                      <td style={{ padding: '3px 6px', color: '#64748b' }}>{s.agent}</td>
                      <td style={{ padding: '3px 6px', color: '#7c3aed' }}>{s.model || s.tool || '—'}</td>
                      <td style={{ padding: '3px 6px', color: s.status === 'success' ? '#16a34a' : s.status === 'failed' ? '#dc2626' : '#ca8a04' }}>{s.status}</td>
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
        </div>
      )}

      {result.note && (
        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 6, padding: '10px 14px', fontSize: 12, color: '#854d0e' }}>
          {result.note}
        </div>
      )}
    </div>
  );
}

export function EvaluationPage() {
  const [scenarios, setScenarios] = useState<any[] | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [requestText, setRequestText] = useState('');
  const [claimId, setClaimId] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'scenarios' | 'unseen'>('scenarios');

  useEffect(() => {
    api.listScenarios()
      .then(d => setScenarios(d.scenarios))
      .catch(err => setError(err?.message || 'Failed to load scenarios'));
  }, []);

  async function runScenario(id: string) {
    setBusy(id);
    setError(null);
    setResult(null);
    try {
      setResult(await api.runScenario(id));
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(null);
    }
  }

  async function runUnseen() {
    if (!requestText.trim()) return;
    setBusy('unseen');
    setError(null);
    setResult(null);
    try {
      setResult(await api.unseenRequest(requestText, claimId || undefined));
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ maxWidth: 980, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: '#0d1117', margin: 0 }}>Evaluation & Unseen Requests</h1>
        <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
          Predefined scenarios use real claims from the challenge dataset. The unseen-request interface demonstrates
          the planner dynamically adapting to arbitrary natural-language investigation requests.
        </p>
      </div>

      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '12px 16px', marginBottom: 16, fontSize: 13, color: '#dc2626', display: 'flex', gap: 8 }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: '#f1f5f9', borderRadius: 8, padding: 4 }}>
        {([['scenarios', 'Predefined Scenarios'], ['unseen', 'Unseen Request']] as const).map(([tab, label]) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '6px 16px', fontSize: 13, fontWeight: 500, borderRadius: 6, border: 'none',
              background: activeTab === tab ? 'white' : 'transparent',
              color: activeTab === tab ? '#0d1117' : '#64748b',
              cursor: 'pointer', boxShadow: activeTab === tab ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'scenarios' && (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '16px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#0d1117', marginBottom: 12 }}>Predefined Evaluation Scenarios</div>
          {!scenarios && <div style={{ fontSize: 13, color: '#94a3b8' }}>Loading scenarios…</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {scenarios?.map((s) => (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', background: '#f8fafc', borderRadius: 6, border: '1px solid #f1f5f9' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#0d1117' }}>{s.name}</div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{s.description}</div>
                </div>
                <button
                  onClick={() => runScenario(s.id)}
                  disabled={busy !== null}
                  style={{
                    padding: '6px 14px', fontSize: 12, fontWeight: 600, borderRadius: 6, border: 'none',
                    background: busy === s.id ? '#94a3b8' : '#156235', color: 'white', cursor: 'pointer', flexShrink: 0,
                  }}
                >
                  {busy === s.id ? 'Running…' : 'Run'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'unseen' && (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '16px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#0d1117', marginBottom: 4 }}>Unseen Investigation Request</div>
          <p style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
            Enter any natural-language investigation request. The planner dynamically determines what models,
            tools, and verification steps are needed — without hard-coded routing.
          </p>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
              Investigation request
            </label>
            <textarea
              value={requestText}
              onChange={e => setRequestText(e.target.value)}
              placeholder="e.g. 'Are there any contradictions in this claim?' or 'Run a full verification with weather and crop checks'"
              rows={3}
              style={{
                width: '100%', padding: '8px 10px', fontSize: 13, border: '1px solid #d1d5db',
                borderRadius: 6, fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box',
              }}
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
              Claim ID (optional — leave blank to use the most recent claim)
            </label>
            <input
              value={claimId}
              onChange={e => setClaimId(e.target.value)}
              placeholder="e.g. CLM-abc123"
              style={{ padding: '7px 10px', fontSize: 13, border: '1px solid #d1d5db', borderRadius: 6, width: '100%', boxSizing: 'border-box' }}
            />
          </div>
          <button
            onClick={runUnseen}
            disabled={!requestText.trim() || busy !== null}
            style={{
              padding: '9px 18px', fontSize: 13, fontWeight: 600, borderRadius: 6, border: 'none',
              background: !requestText.trim() || busy !== null ? '#94a3b8' : '#156235',
              color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            <Zap size={13} /> {busy === 'unseen' ? 'Investigating…' : 'Investigate'}
          </button>
        </div>
      )}

      {/* Result */}
      {result && <ResultPanel result={result} />}
    </div>
  );
}
