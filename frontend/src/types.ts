export type Portal = 'login' | 'farmer' | 'officer' | 'government' | 'admin';

export type ClaimStatus =
  | 'submitted'
  | 'assigned'
  | 'field_verification'
  | 'assessment_completed'
  | 'government_review'
  | 'approved'
  | 'rejected'
  | 'additional_evidence';

export type RiskLevel = 'low' | 'medium' | 'high';
export type DamageSeverity = 'low' | 'moderate' | 'severe' | 'critical';
export type EvidenceType = 'photo' | 'video' | 'document' | 'satellite' | 'weather';

export interface Farmer {
  id: string;
  name: string;
  farmerId: string;
  phone: string;
  village: string;
  taluk: string;
  district: string;
  aadhaarNo: string;
  bankAccount: string;
  ifscCode: string;
}

export interface Land {
  surveyNumber: string;
  area: number;
  cropType: string;
  sowingDate: string;
  expectedYield: number;
  irrigationType: string;
  ownershipType: string;
}

export interface Evidence {
  id: string;
  type: EvidenceType;
  filename: string;
  captureDate: string;
  gpsLat?: number;
  gpsLng?: number;
  uploadedBy: string;
  verified: boolean;
  thumbnailUrl?: string;
  notes?: string;
}

export interface RiskIndicator {
  id: string;
  indicator: string;
  status: 'verified' | 'review_required' | 'no_issue' | 'flagged';
  details: string;
}

export interface DamageAssessment {
  farmerReported: number;
  aiAssisted: number;
  officerAssessed: number | null;
  evidenceConfidence: 'high' | 'medium' | 'low';
  cause: string;
}

export interface TimelineEvent {
  date: string;
  event: string;
  actor: string;
  notes?: string;
}

export interface Claim {
  id: string;
  claimNo: string;
  farmer: Farmer;
  land: Land;
  status: ClaimStatus;
  riskLevel: RiskLevel;
  damageAssessment: DamageAssessment;
  evidence: Evidence[];
  riskIndicators: RiskIndicator[];
  submittedDate: string;
  lastUpdated: string;
  createdAtISO?: string;
  assignedOfficer?: string;
  priority: boolean;
  gpsLat: number;
  gpsLng: number;
  inspectionDate?: string;
  officerNotes?: string;
  recommendation?: 'approve' | 'reject' | 'additional_evidence';
  reliefAmount?: number;
  paymentStatus?: 'pending' | 'processing' | 'paid';
  timeline: TimelineEvent[];
}

export interface Officer {
  id: string;
  name: string;
  employeeId: string;
  designation: string;
  district: string;
  phone: string;
  email: string;
  assignedClaims: number;
  pendingClaims: number;
  completedClaims: number;
}

export interface AuthUser {
  id: string;
  name: string;
  role: Portal;
  designation?: string;
  district?: string;
  employeeId?: string;
  farmerId?: string;
}

export interface DistrictStats {
  district: string;
  claims: number;
  approved: number;
  pending: number;
  rejectedCount: number;
  affectedArea: number;
  avgDamage: number;
}
