const CLASS_BY_STATUS = {
  'Supported by available evidence': 'supported',
  'Partially supported': 'partial',
  'Contradictory evidence found': 'contradictory',
  'Insufficient evidence': 'insufficient',
  'Requires further verification': 'further',
}

export default function StatusBadge({ status }) {
  const cls = CLASS_BY_STATUS[status] || 'further'
  return <span className={`stamp ${cls}`}>{status}</span>
}
