import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'

export default function EvidenceMap({ evidence }) {
  const points = evidence.filter((e) => e.location).map((e) => ({
    id: e.evidence_id,
    lat: e.location.lat,
    lon: e.location.lon,
    label: e.location.label || e.source,
    kind: e.source_kind,
  }))
  if (points.length === 0) return <p className="faint">No located evidence to map.</p>
  const center = [points[0].lat, points[0].lon]
  const color = { source_data: '#33586b', ai_observation: '#5a3a72', external_evidence: '#235e4c', claim: '#6b6350' }
  return (
    <div className="map-box">
      <MapContainer center={center} zoom={14} style={{ height: '100%', width: '100%' }} scrollWheelZoom={false}>
        <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {points.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lon]} radius={7} pathOptions={{ color: color[p.kind] || '#3c6b4a', fillOpacity: 0.7 }}>
            <Popup>{p.label}</Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
