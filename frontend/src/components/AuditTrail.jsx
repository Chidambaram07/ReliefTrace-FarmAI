export default function AuditTrail({ audit }) {
  return (
    <table className="table audit-table">
      <thead>
        <tr><th>step</th><th>agent</th><th>model</th><th>status</th><th>ms</th><th>tokens in/out</th><th>cost</th></tr>
      </thead>
      <tbody>
        {audit.map((a, i) => (
          <tr key={i}>
            <td>{a.step}</td>
            <td>{a.agent}</td>
            <td>{a.model || '\u2014'}</td>
            <td>
              <span className={a.status.startsWith('failed') ? 'pill contradicts' : undefined}>{a.status}</span>
            </td>
            <td>{a.duration_ms}</td>
            <td>{a.input_tokens ?? '\u2014'}/{a.output_tokens ?? '\u2014'}</td>
            <td>{a.cost_estimate_usd != null ? `$${a.cost_estimate_usd}` : '\u2014'}</td>
          </tr>
        ))}
        {audit.filter((a) => a.detail).map((a, i) => (
          <tr key={`detail-${i}`}>
            <td colSpan={7} className="faint" style={{ paddingTop: 0 }}>
              <strong>{a.step}:</strong> {a.detail}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
