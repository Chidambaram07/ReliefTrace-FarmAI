import React, { useState, useMemo } from 'react';
import { Layers, ZoomIn, ZoomOut, Maximize2, Filter } from 'lucide-react';
import type { Claim } from '../types';

interface MapMarker {
  id: string;
  x: number;
  y: number;
  district: string;
  count: number;
  severity: 'low' | 'moderate' | 'severe' | 'critical' | 'risk';
  label?: string;
}

// District → SVG position lookup (geographic mapping to 100×100 viewBox)
const DISTRICT_SVG_POS: Record<string, { x: number; y: number }> = {
  'Chennai': { x: 88, y: 11 }, 'Vellore': { x: 74, y: 17 }, 'Tirupathur': { x: 60, y: 22 },
  'Salem': { x: 50, y: 33 }, 'Nilgiris': { x: 23, y: 40 }, 'Coimbatore': { x: 18, y: 48 },
  'Erode': { x: 37, y: 41 }, 'Namakkal': { x: 56, y: 42 }, 'Trichy': { x: 67, y: 44 },
  'Thanjavur': { x: 82, y: 48 }, 'Nagapattinam': { x: 92, y: 55 }, 'Dindigul': { x: 47, y: 58 },
  'Madurai': { x: 55, y: 65 }, 'Pudukkottai': { x: 75, y: 68 }, 'Sivaganga': { x: 65, y: 74 },
  'Theni': { x: 38, y: 75 }, 'Tiruppur': { x: 22, y: 72 }, 'Virudhunagar': { x: 44, y: 84 },
  'Tirunelveli': { x: 26, y: 84 }, 'Ramanathapuram': { x: 55, y: 90 }, 'Thoothukudi': { x: 32, y: 93 },
  'Kanyakumari': { x: 26, y: 97 }, 'Tamil Nadu': { x: 50, y: 55 },
};

/** Convert real GPS lat/lng → SVG viewBox coordinates for Tamil Nadu */
function gpsToSvg(lat: number, lng: number): { x: number; y: number } | null {
  const latMin = 8, latMax = 13.5, lngMin = 76, lngMax = 80.5;
  if (lat < latMin || lat > latMax || lng < lngMin || lng > lngMax) return null;
  return {
    x: ((lng - lngMin) / (lngMax - lngMin)) * 89 + 7,
    y: ((latMax - lat) / (latMax - latMin)) * 91 + 8,
  };
}

function riskToSeverity(risk: string): MapMarker['severity'] {
  if (risk === 'high') return 'critical';
  if (risk === 'medium') return 'severe';
  return 'moderate';
}

/** Derive district markers + individual claim dots from real claim data */
function computeMapData(claims: Claim[]) {
  // Group by district → markers
  const districtMap = new Map<string, { count: number; highRisk: number; medRisk: number }>();
  claims.forEach(c => {
    const d = c.farmer.district;
    if (!districtMap.has(d)) districtMap.set(d, { count: 0, highRisk: 0, medRisk: 0 });
    const s = districtMap.get(d)!;
    s.count++;
    if (c.riskLevel === 'high') s.highRisk++;
    if (c.riskLevel === 'medium') s.medRisk++;
  });
  const districtMarkers: MapMarker[] = Array.from(districtMap.entries()).map(([district, stats]) => {
    const pos = DISTRICT_SVG_POS[district] || DISTRICT_SVG_POS['Tamil Nadu'] || { x: 50, y: 55 };
    const severity: MapMarker['severity'] =
      stats.highRisk > stats.count * 0.3 ? 'critical' :
      stats.highRisk > 0 ? 'severe' :
      stats.medRisk > stats.count * 0.3 ? 'moderate' : 'low';
    return { id: `d-${district}`, x: pos.x, y: pos.y, district, count: stats.count, severity, label: district };
  });

  // Individual claim dots from GPS coordinates
  const claimDots: { x: number; y: number; severity: 'low' | 'moderate' | 'severe' | 'critical' | 'risk' }[] = claims
    .filter(c => c.gpsLat && c.gpsLng && !(c.gpsLat === 9.25 && c.gpsLng === 77.42)) // skip default fallback GPS
    .map(c => {
      const svgPos = gpsToSvg(c.gpsLat, c.gpsLng);
      if (!svgPos) return null;
      return { ...svgPos, severity: riskToSeverity(c.riskLevel) as 'low' | 'moderate' | 'severe' | 'critical' | 'risk' };
    })
    .filter((d): d is { x: number; y: number; severity: 'low' | 'moderate' | 'severe' | 'critical' | 'risk' } => d !== null);

  return { districtMarkers, claimDots };
}

const severityColor: Record<string, string> = {
  low: '#16a34a',
  moderate: '#eab308',
  severe: '#f97316',
  critical: '#dc2626',
  risk: '#7c3aed',
};

const severityLabel: Record<string, string> = {
  low: 'Low Damage (0–25%)',
  moderate: 'Moderate (26–50%)',
  severe: 'Severe (51–75%)',
  critical: 'Critical (76–100%)',
  risk: 'Risk / Suspicious',
};

// Rough Tamil Nadu outline SVG path (normalized to 100×100 viewBox)
const TN_OUTLINE = `M 88 8 L 82 12 L 76 13 L 70 15 L 63 16 L 56 17 L 48 20 L 42 22 L 36 24 L 30 26 L 24 29 L 19 33 L 14 38 L 10 43 L 8 49 L 10 54 L 10 59 L 8 64 L 7 69 L 9 74 L 11 79 L 14 83 L 18 87 L 20 92 L 21 96 L 25 99 L 27 98 L 29 94 L 32 90 L 36 86 L 40 82 L 43 79 L 47 76 L 50 73 L 53 70 L 56 68 L 58 64 L 60 60 L 63 57 L 67 55 L 71 54 L 74 55 L 77 57 L 79 60 L 82 62 L 86 64 L 90 65 L 93 64 L 95 61 L 96 57 L 95 52 L 93 47 L 93 42 L 92 36 L 91 30 L 90 24 L 89 18 L 88 8 Z`;

interface GISMapProps {
  height?: number;
  showFilters?: boolean;
  fullscreen?: boolean;
  claims?: Claim[];
}

export function GISMap({ height = 420, showFilters = true, fullscreen = false, claims = [] }: GISMapProps) {
  const [hoveredMarker, setHoveredMarker] = useState<MapMarker | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string[]>(['low', 'moderate', 'severe', 'critical', 'risk']);
  const [activeLayer, setActiveLayer] = useState<'claims' | 'damage' | 'risk'>('claims');

  const { districtMarkers, claimDots } = useMemo(() => computeMapData(claims), [claims]);

  const toggleSeverity = (s: string) => {
    setFilterSeverity(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  };

  const visibleMarkers = districtMarkers.filter(m => filterSeverity.includes(m.severity));
  const visibleDots = claimDots.filter(d => filterSeverity.includes(d.severity));

  return (
    <div className={`relative bg-[#1a2634] rounded-lg overflow-hidden border border-[#2d3748] ${fullscreen ? 'h-full' : ''}`} style={fullscreen ? {} : { height }}>
      {/* Map controls */}
      <div className="absolute top-3 left-3 z-20 flex flex-col gap-1.5">
        <button className="w-7 h-7 bg-white/10 hover:bg-white/20 text-white rounded flex items-center justify-center backdrop-blur-sm transition-colors"><ZoomIn size={13} /></button>
        <button className="w-7 h-7 bg-white/10 hover:bg-white/20 text-white rounded flex items-center justify-center backdrop-blur-sm transition-colors"><ZoomOut size={13} /></button>
        <button className="w-7 h-7 bg-white/10 hover:bg-white/20 text-white rounded flex items-center justify-center backdrop-blur-sm transition-colors"><Maximize2 size={13} /></button>
      </div>

      {/* Layer toggle */}
      <div className="absolute top-3 right-3 z-20 flex gap-1">
        {(['claims', 'damage', 'risk'] as const).map(l => (
          <button key={l} onClick={() => setActiveLayer(l)}
            className={`px-2 py-1 text-[10px] font-semibold rounded transition-all backdrop-blur-sm ${activeLayer === l ? 'bg-[#156235] text-white' : 'bg-white/10 text-white/60 hover:bg-white/20'}`}
          >{l.charAt(0).toUpperCase() + l.slice(1)}</button>
        ))}
      </div>

      {/* SVG Map */}
      <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="xMidYMid meet" style={{ height: '100%' }}>
        {/* Background grid */}
        <defs>
          <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="0.3" />
          </pattern>
          <filter id="glow">
            <feGaussianBlur stdDeviation="0.8" result="coloredBlur" />
            <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect width="100" height="100" fill="url(#grid)" />

        {/* Subtle ocean/water background */}
        <rect width="100" height="100" fill="#1e3a5f" opacity="0.3" />

        {/* Tamil Nadu outline */}
        <path d={TN_OUTLINE} fill="#2d4a3e" stroke="#4a7c5f" strokeWidth="0.5" opacity="0.9" />

        {/* Damage heatmap glow spots */}
        {activeLayer === 'damage' && visibleDots.map((dot, i) => (
          <circle key={i} cx={dot.x} cy={dot.y} r="4" fill={severityColor[dot.severity]} opacity="0.15" />
        ))}

        {/* Claim dots */}
        {visibleDots.map((dot, i) => (
          <circle
            key={i}
            cx={dot.x} cy={dot.y} r="1.2"
            fill={severityColor[dot.severity]}
            opacity="0.85"
          />
        ))}

        {/* District markers */}
        {visibleMarkers.map(marker => (
          <g key={marker.id} onMouseEnter={() => setHoveredMarker(marker)} onMouseLeave={() => setHoveredMarker(null)} style={{ cursor: 'pointer' }}>
            <circle
              cx={marker.x} cy={marker.y}
              r={Math.max(3, Math.min(7, marker.count / 35))}
              fill={severityColor[marker.severity]}
              opacity="0.85"
              filter="url(#glow)"
            />
            <circle
              cx={marker.x} cy={marker.y}
              r={Math.max(3, Math.min(7, marker.count / 35)) + 1.5}
              fill="none"
              stroke={severityColor[marker.severity]}
              strokeWidth="0.5"
              opacity="0.4"
            />
            {marker.count >= 100 && (
              <text x={marker.x} y={marker.y + 0.5} textAnchor="middle" dominantBaseline="middle" fill="white" fontSize="2.5" fontWeight="bold">{marker.count}</text>
            )}
          </g>
        ))}

        {/* Hover tooltip */}
        {hoveredMarker && (
          <g>
            <rect
              x={Math.min(hoveredMarker.x - 2, 80)} y={hoveredMarker.y - 14}
              width="26" height="12" rx="1"
              fill="#0d1117" stroke="#2d3748" strokeWidth="0.5" opacity="0.95"
            />
            <text x={Math.min(hoveredMarker.x + 11, 93)} y={hoveredMarker.y - 9} textAnchor="middle" fill="white" fontSize="2.8" fontWeight="600">{hoveredMarker.district}</text>
            <text x={Math.min(hoveredMarker.x + 11, 93)} y={hoveredMarker.y - 5} textAnchor="middle" fill="#94a3b8" fontSize="2.4">{hoveredMarker.count} claims</text>
          </g>
        )}

        {/* Scale bar */}
        <g>
          <line x1="78" y1="95" x2="92" y2="95" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
          <text x="85" y="98" textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize="2.2">50 km</text>
        </g>

        {/* Compass */}
        <g transform="translate(93, 88)">
          <text x="0" y="-3" textAnchor="middle" fill="rgba(255,255,255,0.6)" fontSize="3">N</text>
          <line x1="0" y1="-1" x2="0" y2="2" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
        </g>

        {/* Tamil Nadu label */}
        <text x="42" y="52" textAnchor="middle" fill="rgba(255,255,255,0.12)" fontSize="5" fontWeight="bold" letterSpacing="1">TAMIL NADU</text>
      </svg>

      {/* Legend */}
      <div className="absolute bottom-3 left-3 z-10 flex flex-col gap-1 bg-black/50 backdrop-blur-sm rounded-md p-2">
        {Object.entries(severityLabel).map(([key, label]) => (
          <button
            key={key}
            onClick={() => toggleSeverity(key)}
            className={`flex items-center gap-1.5 text-[10px] font-medium transition-opacity ${filterSeverity.includes(key) ? 'opacity-100' : 'opacity-40'}`}
          >
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: severityColor[key] }} />
            <span className="text-white/80">{label}</span>
          </button>
        ))}
      </div>

      {/* Total claims badge */}
      <div className="absolute bottom-3 right-3 z-10 bg-black/50 backdrop-blur-sm rounded-md px-2.5 py-1.5">
        <p className="text-[10px] text-white/50">Total Claims</p>
        <p className="text-sm font-bold text-white">{claims.length.toLocaleString()}</p>
      </div>
    </div>
  );
}

// Small inline map for claim detail
export function ClaimLocationMap({ lat, lng, verified }: { lat: number; lng: number; verified: boolean }) {
  return (
    <div className="relative bg-[#1a2634] rounded-lg overflow-hidden border border-[#2d3748]" style={{ height: 200 }}>
      <svg viewBox="0 0 100 100" className="w-full h-full">
        <defs>
          <pattern id="grid2" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100" height="100" fill="url(#grid2)" />
        <rect width="100" height="100" fill="#2d4a3e" opacity="0.5" />

        {/* Field boundary simulation */}
        <rect x="30" y="30" width="40" height="40" fill="#4a7c5f" opacity="0.3" stroke="#16a34a" strokeWidth="0.8" strokeDasharray="2,1" rx="1" />
        <rect x="35" y="35" width="30" height="30" fill="#16a34a" opacity="0.15" rx="0.5" />

        {/* Center pin */}
        <circle cx="50" cy="50" r="5" fill={verified ? '#16a34a' : '#eab308'} opacity="0.3" />
        <circle cx="50" cy="50" r="2.5" fill={verified ? '#16a34a' : '#eab308'} />
        <line x1="50" y1="52.5" x2="50" y2="58" stroke={verified ? '#16a34a' : '#eab308'} strokeWidth="1" />
        <circle cx="50" cy="58.5" r="1" fill={verified ? '#16a34a' : '#eab308'} />

        {/* GPS coordinates */}
        <text x="50" y="8" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="3">GPS: {lat.toFixed(3)}° N, {lng.toFixed(3)}° E</text>
      </svg>

      <div className="absolute top-2 right-2">
        <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded ${verified ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'}`}>
          {verified ? '✓ Location Verified' : '⚠ Pending Verification'}
        </span>
      </div>
    </div>
  );
}
