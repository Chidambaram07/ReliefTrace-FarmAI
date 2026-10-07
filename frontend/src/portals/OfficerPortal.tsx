import React, { useState } from 'react';
import {
  ArrowLeft, AlertTriangle, ChevronRight, Filter, Search, Download,
  Camera, MapPin, CheckCircle, Clock, FileText, Star, Send, Eye,
  Upload, Edit2, Save, RefreshCw, ZoomIn, Image, CloudRain, Satellite,
  ShieldAlert, ThumbsUp, ThumbsDown, MoreHorizontal, ExternalLink,
  Loader2
} from 'lucide-react';
import { AppLayout } from '../components/Layout';
import { AuthUser, Claim } from '../types';
import { useClaims, useStats } from '../hooks';
import { computeRiskDistribution } from '../data';
import {
  Badge, Card, KpiCard, Button, Input, Select, Textarea, Alert, Tabs,
  Timeline, ProgressBar, RiskRow, StatRow, SectionHeader, ConfirmModal,
  claimStatusLabel, claimStatusVariant, riskBadgeVariant, Table
} from '../components/ui';
import { GISMap, ClaimLocationMap } from '../components/GISMap';
import { DamageDistributionChart, DamageComparisonChart } from '../components/Charts';

interface OfficerPortalProps { user: AuthUser; onLogout: () => void; }

// ── Evidence Viewer ────────────────────────────────────────────────────────
function EvidenceViewer({ claim }: { claim: Claim }) {
  const [selected, setSelected] = useState(claim.evidence[0]);

  const typeIcon = (type: string) => {
    if (type === 'photo') return <Camera size={12} />;
    if (type === 'satellite') return <Satellite size={12} />;
    if (type === 'weather') return <CloudRain size={12} />;
    return <FileText size={12} />;
  };

  const typeColor = (type: string) => {
    if (type === 'photo') return 'text-blue-600 bg-blue-50 border-blue-200';
    if (type === 'satellite') return 'text-purple-600 bg-purple-50 border-purple-200';
    if (type === 'weather') return 'text-teal-600 bg-teal-50 border-teal-200';
    return 'text-slate-600 bg-slate-50 border-slate-200';
  };

  return (
    <div className="flex gap-5">
      {/* Thumbnail gallery */}
      <div className="w-[180px] flex-shrink-0">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Evidence ({claim.evidence.length})</p>
        <div className="flex flex-col gap-2">
          {claim.evidence.map(ev => (
            <button
              key={ev.id}
              onClick={() => setSelected(ev)}
              className={`flex items-center gap-2.5 p-2 rounded-lg border text-left transition-all ${selected?.id === ev.id ? 'border-[#156235] bg-[#f0fdf4]' : 'border-[#e2e8f0] hover:border-[#cbd5e1] bg-white'}`}
            >
              {ev.thumbnailUrl ? (
                <img src={ev.thumbnailUrl} alt={ev.filename} className="w-10 h-8 object-cover rounded flex-shrink-0 bg-slate-100" />
              ) : (
                <div className="w-10 h-8 bg-slate-100 rounded flex items-center justify-center flex-shrink-0 text-slate-400">
                  {typeIcon(ev.type)}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-medium text-[#1a2130] truncate">{ev.filename}</p>
                <span className={`inline-flex items-center gap-0.5 text-[9px] font-medium px-1 py-0.5 rounded border mt-0.5 ${typeColor(ev.type)}`}>
                  {typeIcon(ev.type)}{ev.type}
                </span>
              </div>
              {ev.verified && <CheckCircle size={12} className="text-green-500 flex-shrink-0" />}
            </button>
          ))}
          <Button variant="outline" size="sm" icon={<Upload size={12} />} className="mt-1">Add Evidence</Button>
        </div>
      </div>

      {/* Main viewer */}
      <div className="flex-1 min-w-0">
        {selected ? (
          <div>
            {/* Main preview */}
            <div className="relative bg-[#1a2634] rounded-xl overflow-hidden mb-3" style={{ height: 300 }}>
              {selected.thumbnailUrl ? (
                <img src={selected.thumbnailUrl} alt={selected.filename} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center text-slate-400">
                  {selected.type === 'satellite' ? <Satellite size={40} /> : selected.type === 'weather' ? <CloudRain size={40} /> : <FileText size={40} />}
                  <p className="text-sm mt-3">{selected.filename}</p>
                </div>
              )}
              <div className="absolute top-3 right-3 flex gap-2">
                <button className="w-7 h-7 bg-black/50 backdrop-blur-sm rounded text-white flex items-center justify-center hover:bg-black/70 transition-colors"><ZoomIn size={13} /></button>
                <button className="w-7 h-7 bg-black/50 backdrop-blur-sm rounded text-white flex items-center justify-center hover:bg-black/70 transition-colors"><ExternalLink size={13} /></button>
              </div>
              {selected.thumbnailUrl && (
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-4">
                  <p className="text-white text-xs font-medium">{selected.filename}</p>
                  <p className="text-white/60 text-[10px] mt-0.5">{selected.captureDate}</p>
                </div>
              )}
            </div>

            {/* Metadata */}
            <div className="grid grid-cols-2 gap-3">
              <Card className="p-4">
                <p className="text-xs font-semibold text-slate-500 mb-3">Evidence Metadata</p>
                <div className="space-y-0">
                  <StatRow label="Capture Date" value={selected.captureDate} />
                  <StatRow label="Uploaded By" value={selected.uploadedBy} />
                  <StatRow label="Type" value={selected.type.charAt(0).toUpperCase() + selected.type.slice(1)} />
                  <StatRow label="Verified" value={selected.verified ? '✓ Verified' : '⏳ Pending'} />
                </div>
              </Card>
              <div className="space-y-3">
                {selected.gpsLat && (
                  <Card className="p-4">
                    <p className="text-xs font-semibold text-slate-500 mb-2">GPS Location</p>
                    <p className="font-mono text-xs text-[#1a2130]">{selected.gpsLat.toFixed(4)}° N, {selected.gpsLng?.toFixed(4)}° E</p>
                    <div className="flex items-center gap-1.5 mt-2">
                      <CheckCircle size={12} className="text-green-500" />
                      <span className="text-xs text-green-600 font-medium">Location Verified</span>
                    </div>
                  </Card>
                )}
                <div className="flex flex-col gap-2">
                  {!selected.verified && (
                    <Button variant="success" size="sm" icon={<CheckCircle size={12} />}>Mark as Verified</Button>
                  )}
                  <Button variant="outline" size="sm" icon={<Download size={12} />}>Download</Button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-48 flex items-center justify-center text-slate-400">
            <div className="text-center">
              <Image size={32} className="mx-auto mb-2 opacity-50" />
              <p className="text-sm">Select evidence to preview</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Damage Assessment Tab ──────────────────────────────────────────────────
function DamageAssessmentTab({ claim, onUpdate }: { claim: Claim; onUpdate: (val: number) => void }) {
  const [officerVal, setOfficerVal] = useState(claim.damageAssessment.officerAssessed ?? 65);
  const da = claim.damageAssessment;
  const diffFarmerAI = Math.abs(da.farmerReported - da.aiAssisted);

  return (
    <div className="space-y-5">
      <Alert type="info">
        <strong>AI-Assisted Assessment</strong> uses satellite imagery analysis and weather data as a decision-support tool. The officer assessment is the authoritative figure.
      </Alert>

      {/* Comparison chart */}
      <Card className="p-5">
        <SectionHeader title="Damage Comparison" subtitle="Reported vs AI estimate vs Officer assessment" className="mb-4" />
        <DamageComparisonChart reported={da.farmerReported} aiAssisted={da.aiAssisted} officerAssessed={da.officerAssessed} />
      </Card>

      {/* Values grid */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4 border-l-4 border-l-red-400">
          <p className="text-xs text-slate-500 font-medium">Farmer Reported</p>
          <p className="text-3xl font-bold text-red-500 mt-1">{da.farmerReported}%</p>
          <p className="text-xs text-slate-400 mt-1">Self-declaration</p>
        </Card>
        <Card className="p-4 border-l-4 border-l-orange-400">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-slate-500 font-medium">AI-Assisted Estimate</p>
              <p className="text-3xl font-bold text-orange-500 mt-1">{da.aiAssisted}%</p>
            </div>
            <span className="text-[9px] bg-orange-50 text-orange-600 border border-orange-200 px-1.5 py-0.5 rounded font-semibold">AI</span>
          </div>
          <p className="text-xs text-slate-400 mt-1">Satellite + weather data</p>
          <p className="text-[10px] text-slate-400 mt-1">Evidence confidence: <strong className={`${da.evidenceConfidence === 'high' ? 'text-green-600' : da.evidenceConfidence === 'medium' ? 'text-amber-600' : 'text-red-500'}`}>{da.evidenceConfidence.charAt(0).toUpperCase() + da.evidenceConfidence.slice(1)}</strong></p>
        </Card>
        <Card className="p-4 border-l-4 border-l-[#156235] bg-[#f0fdf4]">
          <p className="text-xs text-slate-500 font-medium">Officer Assessment</p>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-3xl font-bold text-[#156235]">{officerVal}%</p>
            <span className="text-[10px] bg-[#156235] text-white px-2 py-0.5 rounded font-semibold">FINAL</span>
          </div>
          <p className="text-xs text-slate-400 mt-1">Officer-verified figure</p>
        </Card>
      </div>

      {diffFarmerAI > 15 && (
        <Alert type="warning" title="Discrepancy Detected">
          Farmer reported {da.farmerReported}% but AI estimate is {da.aiAssisted}% — a {diffFarmerAI}% difference. Verify photographic evidence and field notes carefully.
        </Alert>
      )}

      {/* Officer input */}
      <Card className="p-5">
        <SectionHeader title="Officer Damage Entry" subtitle="Enter your verified damage percentage after field inspection" className="mb-4" />
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-slate-600">Verified Damage Percentage</label>
              <span className="font-mono text-2xl font-bold text-[#156235]">{officerVal}%</span>
            </div>
            <input
              type="range" min="0" max="100" value={officerVal}
              onChange={e => setOfficerVal(Number(e.target.value))}
              className="w-full accent-[#156235]"
            />
            <ProgressBar value={officerVal} showValue height={10} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Select label="Cause of Damage (Confirmed)" options={[{ value: 'flood', label: 'Flood' }, { value: 'drought', label: 'Drought' }, { value: 'pest', label: 'Pest / Disease' }, { value: 'wind', label: 'Wind / Storm' }]} defaultValue="flood" />
            <Input label="Inspection Date" type="date" defaultValue={new Date().toISOString().split('T')[0]} />
          </div>
          <Textarea label="Officer Remarks" defaultValue={claim.officerNotes ?? ''} rows={3} placeholder="Record your field observations…" />
          <Button variant="success" size="md" icon={<Save size={14} />} onClick={() => onUpdate(officerVal)}>Save Assessment</Button>
        </div>
      </Card>

      {/* Additional info */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4">
          <p className="text-xs font-semibold text-slate-500 mb-3">Crop Details</p>
          <div className="space-y-0">
            <StatRow label="Crop Type" value={claim.land.cropType} />
            <StatRow label="Sowing Date" value={claim.land.sowingDate} />
            <StatRow label="Cultivated Area" value={`${claim.land.area} acres`} />
            <StatRow label="Expected Yield" value={`${claim.land.expectedYield} tonnes`} />
            <StatRow label="Irrigation" value={claim.land.irrigationType} />
          </div>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-semibold text-slate-500 mb-3">AI Assessment Details</p>
          <div className="space-y-0">
            <StatRow label="Analysis Source" value="AI Verification Engine" />
            <StatRow label="Confidence" value={`${da.evidenceConfidence.charAt(0).toUpperCase() + da.evidenceConfidence.slice(1)}`} />
            <StatRow label="Cause (Reported)" value={da.cause} />
            <StatRow label="Crop" value={claim.land.cropType} />
            <StatRow label="Area" value={claim.land.area > 0 ? `${claim.land.area} acres` : '—'} />
          </div>
          <p className="text-[10px] text-slate-400 mt-3 italic">AI-assisted estimates are for decision support only. Officer assessment is final.</p>
        </Card>
      </div>
    </div>
  );
}

// ── Risk Analysis Tab ──────────────────────────────────────────────────────
function RiskAnalysisTab({ claim }: { claim: Claim }) {
  const flaggedCount = claim.riskIndicators.filter(r => r.status === 'flagged' || r.status === 'review_required').length;
  const riskColor = claim.riskLevel === 'high' ? 'text-red-600 bg-red-50 border-red-200' : claim.riskLevel === 'medium' ? 'text-amber-700 bg-amber-50 border-amber-200' : 'text-green-700 bg-green-50 border-green-200';

  return (
    <div className="space-y-5">
      {/* Risk summary */}
      <div className={`flex items-start gap-4 p-4 rounded-xl border ${riskColor}`}>
        <ShieldAlert size={22} className="flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <p className="font-bold text-base">Risk Level: {claim.riskLevel.toUpperCase()}</p>
          </div>
          <p className="text-sm">
            {claim.riskLevel === 'high'
              ? `${flaggedCount} risk indicator(s) flagged. Thorough verification required before submitting recommendation.`
              : claim.riskLevel === 'medium'
              ? 'Minor inconsistency detected. Further verification recommended before final assessment.'
              : 'All indicators verified. No risk concerns identified.'}
          </p>
        </div>
      </div>

      {/* Indicators */}
      <Card className="p-5">
        <SectionHeader title="Risk Indicators" subtitle="Automated checks applied to this claim" className="mb-4" />
        {claim.riskIndicators.length > 0 ? (
          <div>
            {claim.riskIndicators.map(ri => (
              <RiskRow key={ri.id} indicator={ri.indicator} status={ri.status} details={ri.details} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-400 py-4 text-center">Risk analysis not yet run for this claim.</p>
        )}
      </Card>

      {/* Additional notes */}
      <Card className="p-5">
        <SectionHeader title="Officer Risk Notes" subtitle="Record any additional risk observations" className="mb-4" />
        <Textarea placeholder="Document any inconsistencies, concerns or observations related to this claim's risk profile…" rows={4} />
        <Button variant="outline" size="sm" className="mt-3" icon={<Save size={12} />}>Save Notes</Button>
      </Card>

      <Alert type="warning" title="Risk Terminology Guide">
        Use "Review Required" or "Possible Duplicate" language. Avoid accusations. All risk flags are indicators requiring further investigation — not proof of fraud.
      </Alert>
    </div>
  );
}

// ── Verification Report & Recommendation ─────────────────────────────────
function VerificationReportTab({ claim, onSubmit }: { claim: Claim; onSubmit: (rec: string) => void }) {
  const [recommendation, setRecommendation] = useState<'approve' | 'reject' | 'additional_evidence' | null>(claim.recommendation ?? null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-14 h-14 bg-green-100 rounded-full flex items-center justify-center mb-4">
          <CheckCircle size={28} className="text-green-600" />
        </div>
        <h3 className="text-base font-semibold text-[#1a2130]">Verification Report Submitted</h3>
        <p className="text-sm text-slate-500 mt-2">Claim {claim.claimNo} has been forwarded to the Government Officer for review.</p>
        <Badge variant={recommendation === 'approve' ? 'success' : recommendation === 'reject' ? 'error' : 'warning'} className="mt-3">
          {recommendation === 'approve' ? 'Recommended: Approve' : recommendation === 'reject' ? 'Recommended: Reject' : 'Requested: Additional Evidence'}
        </Badge>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <SectionHeader title="Verification Summary" className="mb-4" />
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Claim Information</p>
            <div className="space-y-0">
              <StatRow label="Claim Number" value={claim.claimNo} mono />
              <StatRow label="Farmer" value={claim.farmer.name} />
              <StatRow label="Village / District" value={`${claim.farmer.village}, ${claim.farmer.district}`} />
              <StatRow label="Crop" value={`${claim.land.cropType} · ${claim.land.area} acres`} />
              <StatRow label="Inspection Date" value={claim.inspectionDate ?? '—'} />
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Assessment Results</p>
            <div className="space-y-0">
              <StatRow label="Farmer Reported" value={`${claim.damageAssessment.farmerReported}%`} />
              <StatRow label="AI Estimate" value={`${claim.damageAssessment.aiAssisted}%`} />
              <StatRow label="Officer Assessment" value={`${claim.damageAssessment.officerAssessed ?? '—'}%`} />
              <StatRow label="Evidence Confidence" value={claim.damageAssessment.evidenceConfidence} />
              <StatRow label="Risk Level" value={claim.riskLevel.toUpperCase()} />
            </div>
          </div>
        </div>
      </Card>

      {/* Evidence reviewed */}
      <Card className="p-5">
        <SectionHeader title="Evidence Reviewed" className="mb-3" />
        <div className="flex flex-wrap gap-2">
          {claim.evidence.map(ev => (
            <span key={ev.id} className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border ${ev.verified ? 'bg-green-50 border-green-200 text-green-700' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>
              {ev.verified ? <CheckCircle size={11} /> : <Clock size={11} />}
              {ev.filename}
            </span>
          ))}
        </div>
      </Card>

      {/* Inspection notes */}
      <Card className="p-5">
        <SectionHeader title="Inspection Notes" className="mb-3" />
        <Textarea defaultValue={claim.officerNotes ?? ''} rows={4} placeholder="Detailed field inspection notes…" />
      </Card>

      {/* Recommendation */}
      <Card className="p-5">
        <SectionHeader title="Officer Recommendation" subtitle="Select your recommendation based on the field investigation" className="mb-4" />
        <div className="grid grid-cols-3 gap-3">
          {[
            { id: 'approve' as const, label: 'Recommend Approval', sub: 'Evidence supports the claim', icon: <ThumbsUp size={16} />, bg: 'border-green-300 bg-green-50', active: 'border-green-500 bg-green-100 ring-2 ring-green-200', text: 'text-green-700' },
            { id: 'reject' as const, label: 'Recommend Rejection', sub: 'Insufficient or conflicting evidence', icon: <ThumbsDown size={16} />, bg: 'border-red-200 bg-red-50', active: 'border-red-400 bg-red-100 ring-2 ring-red-200', text: 'text-red-700' },
            { id: 'additional_evidence' as const, label: 'Request Additional Evidence', sub: 'More information needed', icon: <RefreshCw size={16} />, bg: 'border-amber-200 bg-amber-50', active: 'border-amber-400 bg-amber-100 ring-2 ring-amber-200', text: 'text-amber-700' },
          ].map(opt => (
            <button
              key={opt.id}
              onClick={() => setRecommendation(opt.id)}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all text-center ${recommendation === opt.id ? opt.active : opt.bg} hover:opacity-80`}
            >
              <span className={opt.text}>{opt.icon}</span>
              <p className={`text-xs font-semibold ${opt.text}`}>{opt.label}</p>
              <p className="text-[10px] text-slate-500">{opt.sub}</p>
            </button>
          ))}
        </div>

        {recommendation === 'additional_evidence' && (
          <div className="mt-4">
            <Textarea label="Specify additional evidence required" placeholder="e.g. Clear photographs of damaged crop, panchayat certificate, GPS-verified field video…" rows={2} />
          </div>
        )}
      </Card>

      <div className="flex items-center justify-between pt-2">
        <Button variant="outline">Save Draft</Button>
        <Button
          variant="primary"
          disabled={!recommendation}
          icon={<Send size={14} />}
          onClick={() => setConfirmOpen(true)}
        >
          Submit Verification Report
        </Button>
      </div>

      <ConfirmModal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => { setConfirmOpen(false); setSubmitted(true); onSubmit(recommendation!); }}
        title="Submit Verification Report"
        message={`You are about to submit your verification report for claim ${claim.claimNo} with recommendation: "${recommendation === 'approve' ? 'Recommend Approval' : recommendation === 'reject' ? 'Recommend Rejection' : 'Request Additional Evidence'}". This will forward the claim to the Government Officer for review.`}
        confirmLabel="Submit Report"
        variant="success"
      />
    </div>
  );
}

// ── Claim Verification Workspace ──────────────────────────────────────────
function ClaimVerificationWorkspace({ claim, onBack }: { claim: Claim; onBack: () => void }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [, setOfficerDamage] = useState(claim.damageAssessment.officerAssessed ?? 65);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'farmer-land', label: 'Farmer & Land' },
    { id: 'evidence', label: 'Evidence', count: claim.evidence.length },
    { id: 'damage', label: 'Damage Assessment' },
    { id: 'risk', label: 'Risk Analysis', count: claim.riskIndicators.filter(r => r.status !== 'no_issue').length || undefined },
    { id: 'report', label: 'Report & Recommendation' },
  ];

  return (
    <div className="space-y-4">
      {/* Workspace header */}
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors font-medium">
          <ArrowLeft size={15} />
          Back to Claims
        </button>
        <span className="text-slate-300">/</span>
        <span className="font-mono text-sm text-slate-600">{claim.claimNo}</span>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          {claim.priority && <Badge variant="error" dot>Priority</Badge>}
          <Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge>
          <Badge variant={riskBadgeVariant(claim.riskLevel)}>Risk: {claim.riskLevel.toUpperCase()}</Badge>
        </div>
      </div>

      {/* Claim summary strip */}
      <Card className="p-4">
        <div className="flex items-center gap-6 flex-wrap">
          <div>
            <p className="text-xs text-slate-400">Farmer</p>
            <p className="text-sm font-semibold text-[#1a2130]">{claim.farmer.name}</p>
            <p className="font-mono text-[10px] text-slate-400">{claim.farmer.farmerId}</p>
          </div>
          <div className="h-8 w-px bg-[#e2e8f0] hidden sm:block" />
          <div>
            <p className="text-xs text-slate-400">Village / District</p>
            <p className="text-sm font-medium text-[#1a2130]">{claim.farmer.village}, {claim.farmer.district}</p>
          </div>
          <div className="h-8 w-px bg-[#e2e8f0] hidden sm:block" />
          <div>
            <p className="text-xs text-slate-400">Crop · Area</p>
            <p className="text-sm font-medium text-[#1a2130]">{claim.land.cropType} · {claim.land.area} acres</p>
          </div>
          <div className="h-8 w-px bg-[#e2e8f0] hidden sm:block" />
          <div>
            <p className="text-xs text-slate-400">Reported Loss</p>
            <p className="text-sm font-bold text-red-600">{claim.damageAssessment.farmerReported}%</p>
          </div>
          <div className="h-8 w-px bg-[#e2e8f0] hidden sm:block" />
          <div>
            <p className="text-xs text-slate-400">Cause</p>
            <p className="text-sm font-medium text-[#1a2130]">{claim.damageAssessment.cause}</p>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" size="sm" icon={<Download size={12} />}>Export</Button>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Card>
        <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

        <div className="p-5">
          {/* Overview */}
          {activeTab === 'overview' && (
            <div className="space-y-5">
              <div className="grid grid-cols-3 gap-5">
                <div className="col-span-2 space-y-5">
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Claim Overview</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        ['Farmer', claim.farmer.name],
                        ['Farmer ID', claim.farmer.farmerId],
                        ['Village', claim.farmer.village],
                        ['District', claim.farmer.district],
                        ['Crop', claim.land.cropType],
                        ['Survey No.', claim.land.surveyNumber],
                        ['Cultivated Area', `${claim.land.area} acres`],
                        ['Sowing Date', claim.land.sowingDate],
                        ['Expected Yield', `${claim.land.expectedYield} tonnes`],
                        ['Reported Loss', `${claim.damageAssessment.farmerReported}%`],
                        ['Cause', claim.damageAssessment.cause],
                        ['Submitted', claim.submittedDate],
                      ].map(([k, v]) => (
                        <div key={k} className="flex flex-col">
                          <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">{k}</span>
                          <span className="text-sm font-medium text-[#1a2130] mt-0.5">{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Damage Assessment Summary</p>
                    <div className="space-y-3">
                      <ProgressBar value={claim.damageAssessment.farmerReported} label="Farmer Reported" showValue />
                      <ProgressBar value={claim.damageAssessment.aiAssisted} label="AI-Assisted Estimate" showValue />
                      {claim.damageAssessment.officerAssessed !== null && (
                        <ProgressBar value={claim.damageAssessment.officerAssessed} label="Officer Assessment (Final)" showValue />
                      )}
                    </div>
                  </div>

                  {/* Timeline */}
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Timeline</p>
                    <Timeline items={claim.timeline} />
                  </div>
                </div>

                {/* Right sidebar */}
                <div className="space-y-4">
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">GPS Location</p>
                    <ClaimLocationMap lat={claim.gpsLat} lng={claim.gpsLng} verified={true} />
                    <p className="font-mono text-[10px] text-slate-500 mt-1.5 text-center">{claim.gpsLat.toFixed(4)}° N, {claim.gpsLng.toFixed(4)}° E</p>
                  </div>

                  <Card className="p-4">
                    <p className="text-xs font-semibold text-slate-500 mb-3">Quick Status</p>
                    <div className="space-y-2">
                      {[
                        { label: 'Evidence', val: `${claim.evidence.filter(e => e.verified).length}/${claim.evidence.length} verified`, ok: true },
                        { label: 'GPS Match', val: 'Verified', ok: true },
                        { label: 'Risk Level', val: claim.riskLevel.toUpperCase(), ok: claim.riskLevel === 'low' },
                        { label: 'AI Assessment', val: `${claim.damageAssessment.aiAssisted}%`, ok: true },
                        { label: 'Officer Entry', val: claim.damageAssessment.officerAssessed !== null ? `${claim.damageAssessment.officerAssessed}%` : 'Pending', ok: claim.damageAssessment.officerAssessed !== null },
                      ].map(item => (
                        <div key={item.label} className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">{item.label}</span>
                          <span className={`font-medium ${item.ok ? 'text-green-700' : 'text-amber-700'}`}>{item.val}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              </div>
            </div>
          )}

          {/* Farmer & Land */}
          {activeTab === 'farmer-land' && (
            <div className="grid grid-cols-2 gap-5">
              <Card className="p-5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">Farmer Information</p>
                <div className="flex items-center gap-3 mb-4 pb-4 border-b border-[#e2e8f0]">
                  <div className="w-12 h-12 rounded-full bg-[#f0fdf4] flex items-center justify-center text-[#156235] font-bold text-lg">
                    {claim.farmer.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                  </div>
                  <div>
                    <p className="font-semibold text-[#1a2130]">{claim.farmer.name}</p>
                    <p className="font-mono text-xs text-slate-400">{claim.farmer.farmerId}</p>
                  </div>
                </div>
                <div className="space-y-0">
                  <StatRow label="Village" value={claim.farmer.village} />
                  <StatRow label="Taluk" value={claim.farmer.taluk} />
                  <StatRow label="District" value={claim.farmer.district} />
                  <StatRow label="Mobile" value={claim.farmer.phone} mono />
                  <StatRow label="Aadhaar No." value={claim.farmer.aadhaarNo} mono />
                  <StatRow label="Bank Account" value={claim.farmer.bankAccount} mono />
                  <StatRow label="IFSC Code" value={claim.farmer.ifscCode} mono />
                </div>
              </Card>
              <Card className="p-5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">Land Information</p>
                <div className="space-y-0">
                  <StatRow label="Survey Number" value={claim.land.surveyNumber} mono />
                  <StatRow label="Cultivated Area" value={`${claim.land.area} acres`} />
                  <StatRow label="Crop Type" value={claim.land.cropType} />
                  <StatRow label="Sowing Date" value={claim.land.sowingDate} />
                  <StatRow label="Expected Yield" value={`${claim.land.expectedYield} tonnes`} />
                  <StatRow label="Irrigation Type" value={claim.land.irrigationType} />
                  <StatRow label="Ownership Type" value={claim.land.ownershipType} />
                </div>
                <div className="mt-4 pt-4 border-t border-[#e2e8f0]">
                  <p className="text-xs font-semibold text-slate-500 mb-2">GPS Coordinates</p>
                  <ClaimLocationMap lat={claim.gpsLat} lng={claim.gpsLng} verified={true} />
                </div>
              </Card>
            </div>
          )}

          {activeTab === 'evidence' && <EvidenceViewer claim={claim} />}
          {activeTab === 'damage' && <DamageAssessmentTab claim={claim} onUpdate={setOfficerDamage} />}
          {activeTab === 'risk' && <RiskAnalysisTab claim={claim} />}
          {activeTab === 'report' && <VerificationReportTab claim={claim} onSubmit={() => {}} />}
        </div>
      </Card>
    </div>
  );
}

// ── Claims List ────────────────────────────────────────────────────────────
function ClaimsList({ onViewClaim, claims }: { onViewClaim: (id: string) => void; claims: Claim[] }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');

  const filtered = claims.filter(c => {
    const matchSearch = !search || c.farmer.name.toLowerCase().includes(search.toLowerCase()) || c.claimNo.toLowerCase().includes(search.toLowerCase()) || c.farmer.village.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'all' || c.status === statusFilter;
    const matchRisk = riskFilter === 'all' || c.riskLevel === riskFilter;
    return matchSearch && matchStatus && matchRisk;
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search claims, farmers…" className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-[#e2e8f0] rounded-[6px] focus:outline-none focus:ring-2 focus:ring-[#156235]/25 focus:border-[#156235] transition-all" />
        </div>
        <Select options={[{ value: 'all', label: 'All Status' }, { value: 'submitted', label: 'Submitted' }, { value: 'field_verification', label: 'Field Verification' }, { value: 'assessment_completed', label: 'Assessment Completed' }, { value: 'additional_evidence', label: 'Evidence Requested' }]} value={statusFilter} onChange={e => setStatusFilter(e.target.value)} />
        <Select options={[{ value: 'all', label: 'All Risk' }, { value: 'low', label: 'Low Risk' }, { value: 'medium', label: 'Medium Risk' }, { value: 'high', label: 'High Risk' }]} value={riskFilter} onChange={e => setRiskFilter(e.target.value)} />
        <Button variant="outline" size="sm" icon={<Filter size={13} />}>More Filters</Button>
        <Button variant="outline" size="sm" icon={<Download size={13} />}>Export</Button>
      </div>

      <Card>
        <div className="p-4 border-b border-[#e2e8f0] flex items-center justify-between">
          <p className="text-sm font-semibold text-[#1a2130]">Assigned Claims <span className="font-normal text-slate-400 ml-1">({filtered.length})</span></p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e2e8f0]">
                {['Claim ID', 'Farmer', 'Village', 'Crop', 'Area', 'Reported', 'Risk', 'Status', 'Updated', 'Action'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(claim => (
                <tr key={claim.id} className="border-b border-[#f1f4f8] last:border-0 hover:bg-[#f7f8fa] transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-[#156235] whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      {claim.priority && <Star size={11} className="text-amber-500 fill-amber-500" />}
                      {claim.claimNo.slice(-5)}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium text-[#1a2130] whitespace-nowrap">{claim.farmer.name}</td>
                  <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{claim.farmer.village}</td>
                  <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{claim.land.cropType}</td>
                  <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{claim.land.area} ac</td>
                  <td className="px-4 py-3 font-medium whitespace-nowrap">
                    <span className={`${claim.damageAssessment.farmerReported >= 76 ? 'text-red-600' : claim.damageAssessment.farmerReported >= 51 ? 'text-orange-600' : 'text-amber-600'}`}>{claim.damageAssessment.farmerReported}%</span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Badge variant={riskBadgeVariant(claim.riskLevel)}>{claim.riskLevel.charAt(0).toUpperCase() + claim.riskLevel.slice(1)}</Badge>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{claim.lastUpdated}</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Button variant="primary" size="sm" onClick={() => onViewClaim(claim.id)}>Verify</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ── Officer Dashboard ─────────────────────────────────────────────────────
function OfficerDashboard({ onVerifyClaim, claims }: { onVerifyClaim: (id: string) => void; claims: Claim[] }) {
  const priorityClaims = claims.filter(c => c.priority);

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Claims', value: String(claims.length), icon: <FileText size={16} />, color: 'blue' as const, sub: 'In system' },
          { label: 'Pending Verification', value: String(claims.filter(c => c.status === 'submitted').length), icon: <Clock size={16} />, color: 'amber' as const, sub: 'Awaiting review' },
          { label: 'Verified', value: String(claims.filter(c => c.status === 'assessment_completed' || c.status === 'approved' || c.status === 'rejected').length), icon: <CheckCircle size={16} />, color: 'green' as const, sub: 'Processed' },
          { label: 'Priority Claims', value: String(priorityClaims.length), icon: <AlertTriangle size={16} />, color: 'red' as const, sub: 'Require immediate action' },
        ].map(k => <KpiCard key={k.label} {...k} />)}
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* GIS Map */}
        <div className="col-span-2">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-[#e2e8f0]">
              <h2 className="text-sm font-semibold text-[#1a2130]">Claims Map · Madurai District</h2>
              <Button variant="ghost" size="sm">View Full Map</Button>
            </div>
            <GISMap height={380} claims={claims} />
          </Card>
        </div>

        {/* Damage overview */}
        <div className="space-y-4">
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-[#1a2130] mb-4">Risk Distribution</h3>
            <DamageDistributionChart data={computeRiskDistribution(claims)} />
            <div className="grid grid-cols-2 gap-2 mt-3">
              {computeRiskDistribution(claims).map(d => (
                <div key={d.range} className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
                  <span className="text-[10px] text-slate-500">{d.range}</span>
                  <span className="text-[10px] font-bold text-[#1a2130] ml-auto">{d.count}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-[#1a2130] mb-3">Quick Actions</h3>
            <div className="space-y-2">
              <Button variant="primary" size="sm" className="w-full" icon={<MapPin size={13} />} onClick={() => claims[0] && onVerifyClaim(claims[0].id)}>Start Field Verification</Button>
              <Button variant="outline" size="sm" className="w-full" icon={<Camera size={13} />}>Capture Field Evidence</Button>
              <Button variant="outline" size="sm" className="w-full" icon={<FileText size={13} />}>Submit Report</Button>
            </div>
          </Card>
        </div>
      </div>

      {/* Priority Claims Table */}
      <Card>
        <div className="flex items-center justify-between p-4 border-b border-[#e2e8f0]">
          <h2 className="text-sm font-semibold text-[#1a2130]">Priority Claims <span className="text-amber-500 ml-1">★</span></h2>
          <Button variant="ghost" size="sm" onClick={() => {}}>View All Claims</Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e2e8f0]">
                {['Claim ID', 'Farmer', 'Village', 'Crop', 'Area', 'Reported', 'Risk', 'Status', 'Updated', 'Action'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {claims.map(claim => (
                <tr key={claim.id} className="border-b border-[#f1f4f8] last:border-0 hover:bg-[#f7f8fa] transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-[#156235] whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      {claim.priority && <Star size={11} className="text-amber-500 fill-amber-500" />}
                      {claim.claimNo.slice(-5)}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium text-[#1a2130] whitespace-nowrap">{claim.farmer.name}</td>
                  <td className="px-4 py-3 text-slate-600">{claim.farmer.village}</td>
                  <td className="px-4 py-3 text-slate-600">{claim.land.cropType}</td>
                  <td className="px-4 py-3 text-slate-600">{claim.land.area} ac</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className={`font-medium ${claim.damageAssessment.farmerReported >= 76 ? 'text-red-600' : 'text-orange-600'}`}>{claim.damageAssessment.farmerReported}%</span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap"><Badge variant={riskBadgeVariant(claim.riskLevel)}>{claim.riskLevel}</Badge></td>
                  <td className="px-4 py-3 whitespace-nowrap"><Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge></td>
                  <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{claim.lastUpdated}</td>
                  <td className="px-4 py-3 whitespace-nowrap"><Button variant="primary" size="sm" onClick={() => onVerifyClaim(claim.id)}>Verify →</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ── Main Portal ───────────────────────────────────────────────────────────
export function OfficerPortal({ user, onLogout }: OfficerPortalProps) {
  const [activeNav, setActiveNav] = useState('dashboard');
  const [verifyingClaim, setVerifyingClaim] = useState<string | null>(null);
  const { claims, loading, error, refresh } = useClaims();

  const handleNavChange = (id: string) => {
    setActiveNav(id);
    setVerifyingClaim(null);
  };

  const handleVerifyClaim = (id: string) => {
    setVerifyingClaim(id);
    setActiveNav('verification');
  };

  const getTitle = () => {
    if (verifyingClaim) return undefined;
    if (activeNav === 'dashboard') return 'Officer Dashboard';
    if (activeNav === 'claims') return 'Review Queue';
    if (activeNav === 'map') return 'GIS Map';
    return undefined;
  };

  if (loading) {
    return (
      <AppLayout role="officer" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout} pageTitle="Loading...">
        <div className="flex items-center justify-center py-20">
          <Loader2 size={32} className="animate-spin text-[#156235]" />
          <span className="ml-3 text-slate-500">Loading claims from backend…</span>
        </div>
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout role="officer" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout} pageTitle="Error">
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <AlertTriangle size={32} className="text-red-500 mb-3" />
          <p className="text-red-600 font-medium">{error}</p>
          <p className="text-slate-400 text-sm mt-1">Make sure the backend is running at localhost:8000</p>
          <button onClick={refresh} className="mt-4 text-sm text-[#156235] hover:underline">Retry</button>
        </div>
      </AppLayout>
    );
  }

  const getContent = () => {
    if (verifyingClaim) {
      const claim = claims.find(c => c.id === verifyingClaim) ?? claims[0];
      if (!claim) return <div className="text-center py-10 text-slate-500">No claim found</div>;
      return <ClaimVerificationWorkspace claim={claim} onBack={() => { setVerifyingClaim(null); setActiveNav('claims'); }} />;
    }
    if (activeNav === 'dashboard') return <OfficerDashboard onVerifyClaim={handleVerifyClaim} claims={claims} />;
    if (activeNav === 'claims') return <ClaimsList onViewClaim={handleVerifyClaim} claims={claims} />;
    if (activeNav === 'map') return (
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-[#1a2130]">GIS Claims Map</h2>
        <GISMap height={560} fullscreen claims={claims} />
      </div>
    );
    return <OfficerDashboard onVerifyClaim={handleVerifyClaim} claims={claims} />;
  };

  return (
    <AppLayout role="officer" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout} pageTitle={getTitle()}>
      {getContent()}
    </AppLayout>
  );
}
