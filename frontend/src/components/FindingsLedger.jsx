import Pill from './Pill.jsx'

export default function FindingsLedger({ findings }) {
  return (
    <div className="findings">
      {findings.map((f) => (
        <div className={`finding ${f.weight === 0 ? 'na' : ''}`} key={f.check_id}>
          <div className="f-head">
            <div className="f-title">{f.title}</div>
            <div>
              <Pill tone={f.verdict}>{f.verdict}</Pill>{' '}
              {f.severity && <Pill tone={f.severity}>{f.severity}</Pill>}
            </div>
            <div className="faint">weight {f.weight} &middot; {f.independent ? 'independent' : 'not independent'}</div>
          </div>
          <div>
            <div className="f-detail">{f.detail}</div>
            <div className="f-meta">
              rule: {f.rule}
              {f.evidence_ids.length > 0 && <> &middot; evidence: <span className="mono">{f.evidence_ids.join(', ')}</span></>}
            </div>
            {f.limitations.length > 0 && (
              <div className="f-meta">limitations: {f.limitations.join('; ')}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
