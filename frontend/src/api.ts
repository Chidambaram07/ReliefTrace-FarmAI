/** API client — talks to the ReliefTrace FastAPI backend on AWS API Gateway or local Vite proxy. */

const rawBase = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || 'https://5ydc54f4c2.execute-api.ap-south-1.amazonaws.com').trim();
export const BASE = rawBase.endsWith('/api') ? rawBase : (rawBase === '' ? '/api' : `${rawBase.replace(/\/+$/, '')}/api`);

export class ApiError extends Error {
  code: string;
  status: number;
  details?: string;
  constructor(payload: any, status: number) {
    super(payload?.error?.message || `Request failed (${status})`);
    this.code = payload?.error?.code || 'UNKNOWN';
    this.details = payload?.error?.details;
    this.status = status;
  }
}

async function request<T = any>(path: string, opts: { method?: string; body?: any; isForm?: boolean } = {}): Promise<T> {
  const { method = 'GET', body, isForm = false } = opts;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: isForm ? undefined : body ? { 'Content-Type': 'application/json' } : undefined,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(data, res.status);
  return data as T;
}

// ─── Backend response types ───────────────────────────────────────────

export interface BackendClaim {
  claim_id: string;
  created_at: string;
  status: string;
  provenance?: string;
  claim: {
    farmer_name: string | null;
    village_lgd: string;
    survey_no: string;
    subdivision: string | null;
    claimed_cause: string;
    claimed_crop: string;
    claimed_stage: string | null;
    incident_date: string;
    claimed_lat: number | null;
    claimed_lon: number | null;
    description: string | null;
  };
  images: BackendImage[];
}

export interface BackendImage {
  image_key: number;
  source: string;
  dataset_image_id: string | null;
  filename: string;
  sha256: string;
  mime: string;
  width: number;
  height: number;
  size_bytes: number;
  file_available: boolean;
  exif: { gps_lat: number | null; gps_lon: number | null; captured_at: string | null };
  created_at: string;
}

export interface BackendClaimList {
  total: number;
  limit: number;
  offset: number;
  items: BackendClaim[];
}

export interface BackendHealth {
  status: string;
  version: string;
  time: string;
  database: string;
  dataset_loaded: boolean;
  dataset: { records: number; images: number; images_with_file: number } | null;
  upload_dir_writable: boolean;
  bedrock: { region: string; vision_model_id: string; text_model_id: string };
}

export interface BackendStats {
  claims: number;
  reported: number;
  by_status: Record<string, number>;
  review_open: number;
  review_decided: number;
  ai_calls: number;
}

export interface ReviewQueueItem {
  claim_id: string;
  created_at: string;
  reasons: string[];
  status: string;
  decision: string | null;
  note: string | null;
  decided_at: string | null;
  claimed_cause: string;
  survey_no: string;
  village_lgd: string;
  incident_date: string;
  report_status: string;
  confidence: number;
}

export interface VerificationReport {
  claim_id: string;
  status: string;
  status_reason: string;
  confidence_index: number;
  evidence_consistency_index?: number;
  human_review: { required: boolean; reasons: string[] };
  evidence: any[];
  findings: any[];
  contradictions: string[];
  supporting: string[];
  missing_evidence: string[];
  limitations: string[];
  scores: Record<string, any>;
  timeline: any[];
  narrative?: string;
}

export interface AgenticResult {
  state: any;
  report: {
    claim_id: string;
    status: string;
    status_reason: string;
    plan: any;
    evidence: any[];
    findings: any[];
    supporting: string[];
    contradictions: string[];
    missing_evidence: string[];
    limitations: string[];
    scores: Record<string, any>;
    routing: {
      human_review_required: boolean;
      reasons: string[];
      triggers: Record<string, any>;
    };
    timeline: any[];
    total_latency_ms: number;
  };
  audit_report: {
    total_latency_ms: number;
    status: string;
    trace: any[];
    model_calls: any[];
    tool_results: any[];
  };
}

// ─── API methods ──────────────────────────────────────────────────────

export const api = {
  health: () => request<BackendHealth>('/health'),
  
  // Claims
  createClaim: (claim: any) => request<BackendClaim>('/claims', { method: 'POST', body: claim }),
  listClaims: (limit = 50, offset = 0) => request<BackendClaimList>(`/claims?limit=${limit}&offset=${offset}`),
  getClaim: (id: string) => request<BackendClaim>(`/claims/${id}`),
  uploadImage: (claimId: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request(`/claims/${claimId}/images`, { method: 'POST', body: fd, isForm: true });
  },
  attachDatasetImage: (claimId: string, imageId: string) =>
    request(`/claims/${claimId}/images/from-dataset`, { method: 'POST', body: { image_id: imageId } }),

  // Verification
  verify: (claimId: string, opts: { narrative?: string; analyze?: boolean } = {}) =>
    request<VerificationReport>(
      `/claims/${claimId}/verify?narrative=${opts.narrative ?? 'auto'}&analyze=${opts.analyze ?? true}`,
      { method: 'POST' },
    ),
  verifyAgentic: (claimId: string) =>
    request<AgenticResult>(`/claims/${claimId}/verify-agentic`, { method: 'POST' }),
  getReport: (claimId: string) => request<VerificationReport>(`/claims/${claimId}/report`),

  // Review queue
  reviewQueue: (status = 'open') => request<{ items: ReviewQueueItem[] }>(`/review-queue?status=${status}`),
  decide: (claimId: string, decision: string, note?: string) =>
    request(`/review-queue/${claimId}/decision`, { method: 'POST', body: { decision, note } }),

  // Stats
  stats: () => request<BackendStats>('/stats'),

  // Image file URL
  imageFileUrl: (claimId: string, key: number) => `${BASE}/claims/${claimId}/images/${key}/file`,

  // Evaluation (Phase 13)
  listScenarios: () => request('/evaluation/scenarios'),
  listDemoCases: () => request('/evaluation/demo-cases'),
  runScenario: (id: string) => request(`/evaluation/scenarios/${id}`, { method: 'POST' }),
  unseenRequest: (requestText: string, claimId?: string) =>
    request('/evaluation/unseen-request', {
      method: 'POST',
      body: { request_text: requestText, ...(claimId ? { claim_id: claimId } : {}) },
    }),
};
