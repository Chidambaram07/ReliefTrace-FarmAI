import Pill from './Pill.jsx'

const LEGEND_LABEL = {
  claim: 'Claim',
  source_data: 'Source data',
  ai_observation: 'AI observation',
  external_evidence: 'External evidence',
  derived: 'Derived',
}

export default function EvidenceList({ evidence, legend }) {
  return (
    <div>
      {evidence.map((e) => (
        <div className={`evidence-item ${e.status !== 'available' ? 'unavailable' : ''}`} key={e.evidence_id}>
          <div className="e-top">
            <span className="mono faint">{e.evidence_id}</span>
            <Pill tone={e.source_kind}>{LEGEND_LABEL[e.source_kind] || e.source_kind}</Pill>
          </div>
          <div className="e-source">{e.source}{e.timestamp ? ` \u00b7 ${e.timestamp}` : ''}</div>
          <div className="e-obs">{e.observation}</div>
          {e.limitations.length > 0 && <div className="e-limits">Limitations: {e.limitations.join('; ')}</div>}
        </div>
      ))}
      {legend && (
        <div className="legend-note">
          {Object.entries(legend).map(([k, v]) => (
            <div key={k}><strong>{LEGEND_LABEL[k] || k}:</strong> {v}</div>
          ))}
        </div>
      )}
    </div>
  )
}
