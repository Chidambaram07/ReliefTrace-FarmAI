import Pill from './Pill.jsx'

export default function ScoreBoard({ scores }) {
  if (!scores) return null
  const eci = scores.evidence_consistency_index ?? scores.confidence_index
  return (
    <>
      <div className="scoreboard">
        <div className="score-cell">
          <div className="s-val">{eci}</div>
          <div className="s-label">Evidence Consistency Index / 100</div>
        </div>
        <div className="score-cell">
          <div className="s-val">{Math.round(scores.coverage * 100)}%</div>
          <div className="s-label">coverage of applicable checks</div>
        </div>
        <div className="score-cell">
          <div className="s-val">{Math.round(scores.agreement * 100)}%</div>
          <div className="s-label">agreement among checks seen</div>
        </div>
        <div className="score-cell">
          <div className="s-val">{Math.round(scores.evidence_quality * 100)}%</div>
          <div className="s-label">evidence quality (cited items)</div>
        </div>
      </div>
      <p className="score-note">{scores.formula}</p>
      {Array.isArray(scores.breakdown) && scores.breakdown.length > 0 && (
        <details style={{ marginBottom: '1.2rem' }}>
          <summary className="faint" style={{ cursor: 'pointer' }}>Show per-check point breakdown</summary>
          <ul className="faint" style={{ marginTop: '0.4rem' }}>
            {scores.breakdown.map((r) => (
              <li key={r.check_id}>
                {r.title}: <span className="mono">{r.awarded_points}</span> / {r.max_points} pts
                {' '}(<Pill tone={r.verdict}>{r.verdict}</Pill>, evidence quality {r.evidence_quality})
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  )
}
