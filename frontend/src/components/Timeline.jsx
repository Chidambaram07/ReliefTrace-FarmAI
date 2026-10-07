export default function Timeline({ items }) {
  if (!items?.length) return <p className="faint">No dated evidence to place on a timeline.</p>
  return (
    <div className="timeline">
      {items.map((t, i) => (
        <div className="tl-item" key={i}>
          <div className="tl-when">{t.when || 'undated'}</div>
          <div className="tl-label">{t.label}</div>
        </div>
      ))}
    </div>
  )
}
