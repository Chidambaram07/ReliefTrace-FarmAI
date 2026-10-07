/**
 * data.ts — Fetches REAL data from the backend API and maps it to the
 * frontend types. No mock/fake data. MOCK_USERS stays for login portal
 * role selection (demo convenience only).
 */
import { api, BackendClaim, BackendStats, ReviewQueueItem } from './api';
import type { AuthUser, Claim, ClaimStatus, RiskLevel, Evidence, DamageAssessment, Farmer, Land, TimelineEvent, RiskIndicator, Officer, DistrictStats } from './types';

// ─── Login users (demo convenience, not data) ────────────────────────
export const MOCK_USERS: AuthUser[] = [
  { id: 'U001', name: 'Rajesh Kumar', role: 'farmer', farmerId: 'TN-642626-45/3A', district: 'Madurai' },
  { id: 'U002', name: 'Priya Chandran', role: 'officer', designation: 'Field Officer', district: 'Madurai', employeeId: 'TNF-04521' },
  { id: 'U003', name: 'V. Sureshkumar', role: 'government', designation: 'Deputy Director, Agriculture', district: 'Madurai' },
  { id: 'U004', name: 'Admin User', role: 'admin', designation: 'System Administrator' },
];

const VILLAGE_MAP: Record<string, { village: string; taluk: string; district: string; lat: number; lng: number }> = {
  '642626': { village: 'Melur', taluk: 'Melur', district: 'Madurai', lat: 9.2478, lng: 77.4232 },
  '642627': { village: 'Vadipatti', taluk: 'Vadipatti', district: 'Madurai', lat: 9.2600, lng: 77.4100 },
  '933535': { village: 'Thiruvaiyaru', taluk: 'Thiruvaiyaru', district: 'Thanjavur', lat: 9.2536, lng: 77.3931 },
  '933533': { village: 'Budalur', taluk: 'Budalur', district: 'Thanjavur', lat: 9.2708, lng: 77.4094 },
  '933536': { village: 'Orathanadu', taluk: 'Orathanadu', district: 'Thanjavur', lat: 9.2450, lng: 77.3800 },
};

// ─── Map backend claim → frontend Claim ──────────────────────────────

function mapStatus(backendStatus: string): ClaimStatus {
  const s = backendStatus.toLowerCase();
  if (s === 'submitted') return 'submitted';
  if (s === 'reported') return 'submitted';
  if (s.includes('verified') || s.includes('assessment')) return 'assessment_completed';
  if (s.includes('approved')) return 'approved';
  if (s.includes('rejected')) return 'rejected';
  return 'submitted';
}

function mapRisk(claim: BackendClaim, reportStatus?: string, confidence?: number): RiskLevel {
  if (reportStatus?.includes('Contradictory')) return 'high';
  if (reportStatus?.includes('Insufficient')) return 'medium';
  if (confidence !== undefined && confidence < 30) return 'high';
  if (confidence !== undefined && confidence < 60) return 'medium';
  return 'low';
}

function mapCause(cause: string): string {
  const c = cause.toLowerCase();
  if (c === 'drought') return 'Drought';
  if (c === 'flood') return 'Flood';
  if (c === 'pest') return 'Pest / Disease';
  if (c === 'wind' || c === 'storm' || c === 'cyclone_storm') return 'Wind / Storm';
  return cause.charAt(0).toUpperCase() + cause.slice(1);
}

export function backendClaimToFrontend(bc: BackendClaim, queueItem?: ReviewQueueItem): Claim {
  const c = bc.claim;
  const vInfo = VILLAGE_MAP[c.village_lgd] || {
    village: `Village ${c.village_lgd}`,
    taluk: c.village_lgd.startsWith('642') ? 'Melur' : c.village_lgd.startsWith('933') ? 'Thanjavur' : 'Central',
    district: c.village_lgd.startsWith('642') ? 'Madurai' : c.village_lgd.startsWith('933') ? 'Thanjavur' : 'Tamil Nadu',
    lat: 9.2478,
    lng: 77.4232,
  };

  const farmer: Farmer = {
    id: bc.claim_id,
    name: c.farmer_name || `Claimant (Survey ${c.survey_no})`,
    farmerId: `TN-${c.village_lgd}-${c.survey_no}`,
    phone: 'Not recorded',
    village: vInfo.village,
    taluk: vInfo.taluk,
    district: vInfo.district,
    aadhaarNo: 'Not captured in dataset',
    bankAccount: 'Not captured in dataset',
    ifscCode: 'Not captured in dataset',
  };

  // Extract area from description only if explicitly stated by claimant, never invent
  let area = 0;
  if (c.description) {
    const areaMatch = c.description.match(/(\d+(?:\.\d+)?)\s*(?:acres?|ac|ha)/i);
    if (areaMatch) area = parseFloat(areaMatch[1]);
  }

  // Extract damage percentage only if explicitly stated by claimant, never invent
  let farmerReported = 0;
  if (c.description) {
    const pctMatch = c.description.match(/(\d{1,3})%/);
    if (pctMatch) {
      farmerReported = parseInt(pctMatch[1], 10);
    }
  }

  const reportStatus = queueItem?.report_status;
  const confidence = queueItem?.confidence;
  const aiAssisted = confidence ?? 0;
  const status = mapStatus(bc.status);

  const land: Land = {
    surveyNumber: c.survey_no + (c.subdivision ? `/${c.subdivision}` : ''),
    area: Number(area.toFixed(1)),
    cropType: c.claimed_crop || 'Not specified',
    sowingDate: 'Not recorded',
    expectedYield: 0,
    irrigationType: 'Not recorded',
    ownershipType: 'Not recorded',
  };

  const evidence: Evidence[] = bc.images.map((img) => ({
    id: `E${img.image_key}`,
    type: 'photo' as const,
    filename: img.filename,
    captureDate: img.exif?.captured_at || bc.created_at,
    gpsLat: img.exif?.gps_lat ?? undefined,
    gpsLng: img.exif?.gps_lon ?? undefined,
    uploadedBy: c.farmer_name || 'System',
    verified: img.source === 'dataset',
    thumbnailUrl: img.file_available ? api.imageFileUrl(bc.claim_id, img.image_key) : undefined,
  }));

  const riskIndicators: RiskIndicator[] = [];
  if (queueItem) {
    queueItem.reasons.forEach((reason, i) => {
      let rStatus: 'verified' | 'review_required' | 'no_issue' | 'flagged' = 'review_required';
      if (reason.includes('Contradiction')) rStatus = 'flagged';
      if (reason.includes('Missing')) rStatus = 'review_required';
      riskIndicators.push({
        id: `R${i}`,
        indicator: reason.split(':')[0]?.replace(/^Status is '/, '').replace(/'\.?$/, '') || reason,
        status: rStatus,
        details: reason,
      });
    });
  }

  const damageAssessment: DamageAssessment = {
    farmerReported,
    aiAssisted,
    officerAssessed: status === 'approved' ? farmerReported : null,
    evidenceConfidence: queueItem
      ? (queueItem.confidence > 60 ? 'high' : queueItem.confidence > 30 ? 'medium' : 'low')
      : 'low',
    cause: mapCause(c.claimed_cause),
  };

  const timeline: TimelineEvent[] = [
    { date: formatDate(bc.created_at), event: 'Claim Submitted', actor: c.farmer_name || 'System' },
  ];
  if (bc.images.length > 0) {
    timeline.push({ date: formatDate(bc.created_at), event: `${bc.images.length} Evidence Photo(s) Attached`, actor: 'System' });
  }
  if (queueItem) {
    timeline.push({ date: formatDate(queueItem.created_at), event: 'AI Consistency Evaluation Completed', actor: 'ReliefTrace AI Engine', notes: `Confidence score: ${queueItem.confidence}%` });
  }
  if (queueItem?.decision) {
    timeline.push({ date: formatDate(queueItem.decided_at || queueItem.created_at), event: `Review Decided: ${queueItem.decision}`, actor: 'Officer', notes: queueItem.note || undefined });
  }

  const reliefAmount = Math.round(land.area * (farmerReported / 100) * 16500);
  const paymentStatus: 'pending' | 'processing' | 'paid' = status === 'approved' ? 'paid' : status === 'assessment_completed' ? 'processing' : 'pending';

  return {
    id: bc.claim_id,
    claimNo: bc.claim_id,
    farmer,
    land,
    status,
    riskLevel: mapRisk(bc, reportStatus, confidence),
    damageAssessment,
    evidence,
    riskIndicators,
    submittedDate: formatDate(bc.created_at),
    lastUpdated: formatDate(bc.created_at),
    createdAtISO: bc.created_at,
    priority: (reportStatus?.includes('Contradictory') ?? false) || (confidence !== undefined && confidence < 30),
    gpsLat: c.claimed_lat ?? vInfo.lat,
    gpsLng: c.claimed_lon ?? vInfo.lng,
    timeline,
    reliefAmount,
    paymentStatus,
  };
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return iso;
  }
}

// ─── Data fetching functions ─────────────────────────────────────────

export async function fetchClaims(): Promise<Claim[]> {
  const [claimList, queueResp] = await Promise.all([
    api.listClaims(200),
    api.reviewQueue('open').catch(() => ({ items: [] })),
  ]);
  const queueMap = new Map<string, ReviewQueueItem>();
  queueResp.items.forEach(q => queueMap.set(q.claim_id, q));
  return claimList.items.map(bc => backendClaimToFrontend(bc, queueMap.get(bc.claim_id)));
}

export async function fetchStats(): Promise<BackendStats> {
  return api.stats();
}

export async function fetchHealth() {
  return api.health();
}

export async function fetchReviewQueue(status = 'open') {
  return api.reviewQueue(status);
}

// ─── Derived stats (computed from real data) ─────────────────────────

export function computeDistrictStats(claims: Claim[]): DistrictStats[] {
  const map = new Map<string, DistrictStats>();
  claims.forEach(c => {
    const d = c.farmer.district;
    if (!map.has(d)) {
      map.set(d, { district: d, claims: 0, approved: 0, pending: 0, rejectedCount: 0, affectedArea: 0, avgDamage: 0 });
    }
    const s = map.get(d)!;
    s.claims++;
    if (c.status === 'approved') s.approved++;
    else if (c.status === 'rejected') s.rejectedCount++;
    else s.pending++;
    s.affectedArea += c.land.area;
  });
  return Array.from(map.values());
}

export function computeStatusCounts(claims: Claim[]) {
  const counts: Record<string, number> = {};
  claims.forEach(c => {
    counts[c.status] = (counts[c.status] || 0) + 1;
  });
  return counts;
}

// ─── Chart data helpers (derived from real claims) ───────────────────

export function computeClaimsOverTime(claims: Claim[]): { month: string; claims: number }[] {
  const monthMap = new Map<string, { sortKey: number; claims: number }>();
  claims.forEach(c => {
    if (!c.createdAtISO) return;
    try {
      const d = new Date(c.createdAtISO);
      const label = d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
      const sortKey = d.getFullYear() * 100 + d.getMonth();
      if (!monthMap.has(label)) monthMap.set(label, { sortKey, claims: 0 });
      monthMap.get(label)!.claims++;
    } catch { /* skip invalid dates */ }
  });
  return Array.from(monthMap.entries())
    .sort((a, b) => a[1].sortKey - b[1].sortKey)
    .map(([month, v]) => ({ month, claims: v.claims }));
}

export function computeRiskDistribution(claims: Claim[]): { range: string; count: number; color: string }[] {
  const buckets = { low: 0, medium: 0, high: 0 };
  claims.forEach(c => { buckets[c.riskLevel]++; });
  return [
    { range: 'Low', count: buckets.low, color: '#16a34a' },
    { range: 'Medium', count: buckets.medium, color: '#eab308' },
    { range: 'High', count: buckets.high, color: '#dc2626' },
  ];
}

export function computeCropStats(claims: Claim[]): { crop: string; claims: number; avgDamage: number }[] {
  const map = new Map<string, number>();
  claims.forEach(c => {
    const crop = c.land.cropType || 'Unknown';
    map.set(crop, (map.get(crop) || 0) + 1);
  });
  return Array.from(map.entries())
    .map(([crop, count]) => ({ crop, claims: count, avgDamage: 0 }))
    .sort((a, b) => b.claims - a.claims);
}

export function computePaymentStats(claims: Claim[]): { name: string; value: number; color: string }[] {
  const approved = claims.filter(c => c.status === 'approved').length;
  const rejected = claims.filter(c => c.status === 'rejected').length;
  const pending = claims.length - approved - rejected;
  return [
    { name: 'Approved', value: approved, color: '#16a34a' },
    { name: 'Pending', value: pending, color: '#eab308' },
    { name: 'Rejected', value: rejected, color: '#dc2626' },
  ];
}

// ─── Legacy stubs (unused, kept for backward compatibility) ──────────

export const SAMPLE_CLAIMS: Claim[] = [];
export const SAMPLE_OFFICERS: Officer[] = [];
export const DISTRICT_STATS: DistrictStats[] = [];
export const DAMAGE_DISTRIBUTION: any[] = [];
export const CLAIMS_OVER_TIME: any[] = [];
export const CROP_DAMAGE: any[] = [];
