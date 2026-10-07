import React, { useState } from 'react';
import {
  FileText, CheckCircle, Clock, XCircle, CreditCard, BarChart2,
  Download, ArrowLeft, ThumbsUp, ThumbsDown, RefreshCw, ChevronRight,
  AlertTriangle, MapPin, TrendingUp, Users, Loader2
} from 'lucide-react';
import { AppLayout } from '../components/Layout';
import { AuthUser, Claim } from '../types';
import { useClaims, useStats, useDistrictStats } from '../hooks';
import { computeClaimsOverTime, computeCropStats, computePaymentStats } from '../data';
import {
  Badge, Card, KpiCard, Button, Textarea, Alert, Tabs,
  Timeline, ProgressBar, RiskRow, StatRow, SectionHeader, ConfirmModal,
  claimStatusLabel, claimStatusVariant, riskBadgeVariant
} from '../components/ui';
import { GISMap } from '../components/GISMap';
import { DistrictClaimsChart, CropDamageChart, ClaimStatusDonut, ReliefPaymentChart, DamageComparisonChart, MonthlyTrendChart } from '../components/Charts';

interface GovPortalProps { user: AuthUser; onLogout: () => void; }

// ── Claim Review Workspace ─────────────────────────────────────────────────
function ClaimReviewWorkspace({ claim, onBack, onDecision }: { claim: Claim; onBack: () => void; onDecision: (decision: string) => void }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [decisionModal, setDecisionModal] = useState<'approve' | 'reject' | 'additional' | null>(null);
  const [decided, setDecided] = useState(false);
  const [finalDecision, setFinalDecision] = useState<string | null>(null);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'officer-report', label: 'Officer Report' },
    { id: 'evidence', label: 'Evidence' },
    { id: 'risk', label: 'Risk Analysis' },
    { id: 'history', label: 'History' },
  ];

  if (decided) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 ${finalDecision === 'approve' ? 'bg-green-100' : finalDecision === 'reject' ? 'bg-red-100' : 'bg-amber-100'}`}>
          {finalDecision === 'approve' ? <CheckCircle size={32} className="text-green-600" /> : finalDecision === 'reject' ? <XCircle size={32} className="text-red-600" /> : <RefreshCw size={32} className="text-amber-600" />}
        </div>
        <h3 className="text-lg font-bold text-[#1a2130]">{finalDecision === 'approve' ? 'Claim Approved' : finalDecision === 'reject' ? 'Claim Rejected' : 'Additional Verification Requested'}</h3>
        <p className="text-sm text-slate-500 mt-2 mb-1">{claim.claimNo}</p>
        <p className="text-sm text-slate-500 mb-6">{claim.farmer.name} · {claim.farmer.village}</p>
        {finalDecision === 'approve' && (
          <div className="bg-[#f0fdf4] border border-green-200 rounded-xl p-5 mb-6">
            <p className="text-sm text-slate-600">Approved Relief Amount</p>
            <p className="text-3xl font-bold text-[#156235] mt-1">₹{claim.reliefAmount?.toLocaleString('en-IN') ?? '—'}</p>
            <p className="text-xs text-slate-500 mt-2">Will be processed to IFSC {claim.farmer.ifscCode} · Account ending {claim.farmer.bankAccount}</p>
          </div>
        )}
        <Button onClick={onBack} icon={<ArrowLeft size={14} />}>Back to Claims</Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 font-medium transition-colors">
          <ArrowLeft size={15} /> Back to Verified Claims
        </button>
        <span className="text-slate-300">/</span>
        <span className="font-mono text-sm text-slate-600">{claim.claimNo}</span>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge>
          <Badge variant={riskBadgeVariant(claim.riskLevel)}>Risk: {claim.riskLevel.toUpperCase()}</Badge>
        </div>
      </div>

      {/* Summary strip */}
      <Card className="p-4">
        <div className="flex items-center gap-6 flex-wrap">
          {[
            ['Farmer', claim.farmer.name], ['Village', `${claim.farmer.village}, ${claim.farmer.district}`],
            ['Crop', `${claim.land.cropType} · ${claim.land.area} ac`], ['Damage (Officer)', `${claim.damageAssessment.officerAssessed ?? claim.damageAssessment.farmerReported}%`],
            ['Officer Rec.', claim.recommendation === 'approve' ? 'Approve' : claim.recommendation === 'reject' ? 'Reject' : 'Add. Evidence'],
          ].map(([k, v]) => (
            <div key={k}>
              <p className="text-[10px] text-slate-400">{k}</p>
              <p className={`text-sm font-medium ${k === "Officer Rec." ? (claim.recommendation === 'approve' ? 'text-green-600' : claim.recommendation === 'reject' ? 'text-red-600' : 'text-amber-600') : 'text-[#1a2130]'}`}>{v}</p>
            </div>
          ))}
          <div className="ml-auto"><Button variant="outline" size="sm" icon={<Download size={12} />}>Export Report</Button></div>
        </div>
      </Card>

      {/* Decision panel */}
      <Card className="p-5 border-2 border-[#156235]/20 bg-[#f0fdf4]">
        <SectionHeader title="Final Decision" subtitle="Review all information before making your decision. This action will be recorded in the audit log." className="mb-4" />
        <div className="grid grid-cols-3 gap-3">
          <Button variant="success" size="md" icon={<ThumbsUp size={15} />} onClick={() => setDecisionModal('approve')}>Approve Claim</Button>
          <Button variant="danger" size="md" icon={<ThumbsDown size={15} />} onClick={() => setDecisionModal('reject')}>Reject Claim</Button>
          <Button variant="outline" size="md" icon={<RefreshCw size={15} />} onClick={() => setDecisionModal('additional')}>Request Additional Verification</Button>
        </div>
        {claim.recommendation && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-xs text-slate-500">Officer Recommendation:</span>
            <Badge variant={claim.recommendation === 'approve' ? 'success' : claim.recommendation === 'reject' ? 'error' : 'warning'}>
              {claim.recommendation === 'approve' ? 'Recommend Approval' : claim.recommendation === 'reject' ? 'Recommend Rejection' : 'Add. Evidence Required'}
            </Badge>
          </div>
        )}
      </Card>

      {/* Tabs */}
      <Card>
        <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />
        <div className="p-5">
          {activeTab === 'overview' && (
            <div className="grid grid-cols-2 gap-5">
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Farmer & Land</p>
                  <div className="space-y-0">
                    <StatRow label="Farmer Name" value={claim.farmer.name} />
                    <StatRow label="Farmer ID" value={claim.farmer.farmerId} mono />
                    <StatRow label="Village / District" value={`${claim.farmer.village}, ${claim.farmer.district}`} />
                    <StatRow label="Survey Number" value={claim.land.surveyNumber} mono />
                    <StatRow label="Cultivated Area" value={`${claim.land.area} acres`} />
                    <StatRow label="Crop Type" value={claim.land.cropType} />
                    <StatRow label="Irrigation" value={claim.land.irrigationType} />
                  </div>
                </div>
              </div>
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Damage Assessment</p>
                  <DamageComparisonChart reported={claim.damageAssessment.farmerReported} aiAssisted={claim.damageAssessment.aiAssisted} officerAssessed={claim.damageAssessment.officerAssessed} />
                </div>
                <div className="space-y-2">
                  <ProgressBar value={claim.damageAssessment.farmerReported} label="Farmer Reported" showValue />
                  <ProgressBar value={claim.damageAssessment.aiAssisted} label="AI Estimate" showValue />
                  {claim.damageAssessment.officerAssessed !== null && <ProgressBar value={claim.damageAssessment.officerAssessed} label="Officer Assessment (Final)" showValue />}
                </div>
              </div>
            </div>
          )}
          {activeTab === 'officer-report' && (
            <div className="space-y-4">
              <Card className="p-4">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Field Officer Report</p>
                <div className="space-y-0 mb-4">
                  <StatRow label="Officer" value={claim.assignedOfficer ?? '—'} />
                  <StatRow label="Inspection Date" value={claim.inspectionDate ?? '—'} />
                  <StatRow label="GPS Verified" value={claim.gpsLat ? `Yes — ${claim.gpsLat.toFixed(3)}°N, ${claim.gpsLng.toFixed(3)}°E` : '—'} />
                  <StatRow label="Officer Damage Estimate" value={`${claim.damageAssessment.officerAssessed ?? '—'}%`} />
                  <StatRow label="Evidence Count" value={`${claim.evidence.length} items reviewed`} />
                  <StatRow label="Risk Level" value={claim.riskLevel.toUpperCase()} />
                  <StatRow label="Recommendation" value={claim.recommendation ?? '—'} />
                </div>
                {claim.officerNotes && (
                  <div>
                    <p className="text-xs font-medium text-slate-500 mb-2">Inspection Notes</p>
                    <div className="bg-[#f7f8fa] border border-[#e2e8f0] rounded-lg p-3 text-sm text-slate-600 leading-relaxed">{claim.officerNotes}</div>
                  </div>
                )}
              </Card>
            </div>
          )}
          {activeTab === 'evidence' && (
            <div className="grid grid-cols-3 gap-3">
              {claim.evidence.map(ev => (
                <div key={ev.id} className="border border-[#e2e8f0] rounded-lg overflow-hidden">
                  {ev.thumbnailUrl ? (
                    <img src={ev.thumbnailUrl} alt={ev.filename} className="w-full h-28 object-cover bg-slate-100" />
                  ) : (
                    <div className="w-full h-28 bg-slate-100 flex items-center justify-center text-slate-400">
                      <FileText size={24} />
                    </div>
                  )}
                  <div className="p-2.5">
                    <p className="text-xs font-medium text-[#1a2130] truncate">{ev.filename}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{ev.captureDate}</p>
                    <div className="flex items-center gap-1 mt-1">
                      {ev.verified ? <CheckCircle size={10} className="text-green-500" /> : <Clock size={10} className="text-amber-500" />}
                      <span className="text-[10px] text-slate-400">{ev.verified ? 'Verified' : 'Pending'}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          {activeTab === 'risk' && (
            <div className="space-y-4">
              <div className={`flex items-center gap-3 p-4 rounded-xl border ${claim.riskLevel === 'high' ? 'bg-red-50 border-red-200' : claim.riskLevel === 'medium' ? 'bg-amber-50 border-amber-200' : 'bg-green-50 border-green-200'}`}>
                <AlertTriangle size={18} className={claim.riskLevel === 'high' ? 'text-red-600' : claim.riskLevel === 'medium' ? 'text-amber-600' : 'text-green-600'} />
                <p className="text-sm font-semibold">Overall Risk: {claim.riskLevel.toUpperCase()}</p>
              </div>
              {claim.riskIndicators.map(ri => (
                <RiskRow key={ri.id} indicator={ri.indicator} status={ri.status} details={ri.details} />
              ))}
            </div>
          )}
          {activeTab === 'history' && <Timeline items={claim.timeline} />}
        </div>
      </Card>

      {/* Confirm modals */}
      <ConfirmModal
        open={decisionModal === 'approve'}
        onClose={() => setDecisionModal(null)}
        onConfirm={() => { setDecisionModal(null); setFinalDecision('approve'); setDecided(true); onDecision('approve'); }}
        title="Approve Claim"
        message={`You are about to approve claim ${claim.claimNo} for farmer ${claim.farmer.name}. Relief amount of ₹${claim.reliefAmount?.toLocaleString('en-IN') ?? 'TBD'} will be initiated for processing. This action will be recorded in the audit log.`}
        confirmLabel="Approve Claim"
        variant="success"
      />
      <ConfirmModal
        open={decisionModal === 'reject'}
        onClose={() => setDecisionModal(null)}
        onConfirm={() => { setDecisionModal(null); setFinalDecision('reject'); setDecided(true); onDecision('reject'); }}
        title="Reject Claim"
        message={`You are about to reject claim ${claim.claimNo} for farmer ${claim.farmer.name}. The farmer will be notified with the reason for rejection. This action is recorded in the audit log.`}
        confirmLabel="Reject Claim"
        variant="danger"
      />
      <ConfirmModal
        open={decisionModal === 'additional'}
        onClose={() => setDecisionModal(null)}
        onConfirm={() => { setDecisionModal(null); setFinalDecision('additional'); setDecided(true); onDecision('additional'); }}
        title="Request Additional Verification"
        message={`You are about to return claim ${claim.claimNo} for additional field verification. The assigned officer will be notified to conduct further investigation.`}
        confirmLabel="Request Verification"
        variant="warning"
      />
    </div>
  );
}

// ── Analytics Screen ──────────────────────────────────────────────────────
function AnalyticsScreen({ claims }: { claims: Claim[] }) {
  const districtStats = useDistrictStats(claims);
  const statusCounts = claims.reduce((acc, c) => { acc[c.status] = (acc[c.status] || 0) + 1; return acc; }, {} as Record<string, number>);
  const approved = statusCounts['approved'] || 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Claims', value: String(claims.length), icon: <FileText size={16} />, color: 'blue' as const },
          { label: 'Verified', value: String(claims.filter(c => c.status === 'assessment_completed' || c.status === 'approved').length), icon: <CheckCircle size={16} />, color: 'green' as const },
          { label: 'Approved', value: String(approved), icon: <ThumbsUp size={16} />, color: 'green' as const },
          { label: 'High Risk', value: String(claims.filter(c => c.riskLevel === 'high').length), icon: <AlertTriangle size={16} />, color: 'red' as const },
        ].map(k => <KpiCard key={k.label} {...k} />)}
      </div>
      <div className="grid grid-cols-2 gap-5">
        <Card className="p-5">
          <SectionHeader title="Claims by District" className="mb-4" />
          <DistrictClaimsChart data={districtStats} />
        </Card>
        <Card className="p-5">
          <SectionHeader title="Crop-wise Damage Analysis" className="mb-4" />
          <CropDamageChart data={computeCropStats(claims)} />
        </Card>
        <Card className="p-5">
          <SectionHeader title="Claim Status Distribution" className="mb-4" />
          <ClaimStatusDonut data={[
            { name: 'Approved', value: statusCounts['approved'] || 0, color: '#16a34a' },
            { name: 'Assessment Done', value: statusCounts['assessment_completed'] || 0, color: '#1e40af' },
            { name: 'Submitted', value: statusCounts['submitted'] || 0, color: '#94a3b8' },
            { name: 'Rejected', value: statusCounts['rejected'] || 0, color: '#dc2626' },
          ]} />
        </Card>
        <Card className="p-5">
          <SectionHeader title="Monthly Claim Trend" className="mb-4" />
          <MonthlyTrendChart data={computeClaimsOverTime(claims)} />
        </Card>
      </div>

      {/* District table */}
      <Card>
        <div className="flex items-center justify-between p-4 border-b border-[#e2e8f0]">
          <h2 className="text-sm font-semibold text-[#1a2130]">District Summary</h2>
          <Button variant="outline" size="sm" icon={<Download size={12} />}>Export</Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e2e8f0]">
                {['District', 'Claims', 'Approved', 'Pending', 'Rejected', 'Affected Area', 'Avg Damage'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {districtStats.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-400">No district data yet</td></tr>
              ) : districtStats.map(d => (
                <tr key={d.district} className="border-b border-[#f1f4f8] last:border-0 hover:bg-[#f7f8fa] transition-colors">
                  <td className="px-4 py-3 font-medium text-[#1a2130]">{d.district}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-[#1a2130]">{d.claims}</td>
                  <td className="px-4 py-3"><Badge variant="success">{d.approved}</Badge></td>
                  <td className="px-4 py-3"><Badge variant="warning">{d.pending}</Badge></td>
                  <td className="px-4 py-3"><Badge variant="error">{d.rejectedCount}</Badge></td>
                  <td className="px-4 py-3 text-slate-600">{d.affectedArea} ac</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <ProgressBar value={d.avgDamage} height={6} className="flex-1" />
                      <span className="text-xs font-medium text-slate-600 w-8">{d.avgDamage}%</span>
                    </div>
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

// ── Government Dashboard ──────────────────────────────────────────────────
function GovDashboard({ claims, onReviewClaim, showTableOnly }: { claims: Claim[]; onReviewClaim: (id: string) => void; showTableOnly?: boolean }) {
  const approved = claims.filter(c => c.status === 'approved').length;
  const rejected = claims.filter(c => c.status === 'rejected').length;
  const pending = claims.length - approved - rejected;

  const claimsTable = (
    <Card>
      <div className="flex items-center justify-between p-4 border-b border-[#e2e8f0]">
        <h2 className="text-sm font-semibold text-[#1a2130]">Claims Awaiting Decision</h2>
        <Button variant="outline" size="sm" icon={<Download size={12} />}>Export</Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#e2e8f0]">
              {['Claim ID', 'Farmer', 'District', 'Crop', 'Officer Damage', 'Risk', 'Officer Rec.', 'Status', 'Action'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {claims.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-sm text-slate-400">No claims loaded</td></tr>
            ) : claims.map(claim => (
              <tr key={claim.id} className="border-b border-[#f1f4f8] last:border-0 hover:bg-[#f7f8fa] transition-colors">
                <td className="px-4 py-3 font-mono text-xs text-[#156235]">{claim.claimNo.slice(-5)}</td>
                <td className="px-4 py-3 font-medium text-[#1a2130]">{claim.farmer.name}</td>
                <td className="px-4 py-3 text-slate-600">{claim.farmer.district}</td>
                <td className="px-4 py-3 text-slate-600">{claim.land.cropType}</td>
                <td className="px-4 py-3 font-medium">{claim.damageAssessment.officerAssessed ?? '—'}%</td>
                <td className="px-4 py-3"><Badge variant={riskBadgeVariant(claim.riskLevel)}>{claim.riskLevel}</Badge></td>
                <td className="px-4 py-3">
                  {claim.recommendation ? (
                    <Badge variant={claim.recommendation === 'approve' ? 'success' : claim.recommendation === 'reject' ? 'error' : 'warning'}>
                      {claim.recommendation === 'approve' ? 'Approve' : claim.recommendation === 'reject' ? 'Reject' : 'Add. Evidence'}
                    </Badge>
                  ) : <span className="text-slate-400 text-xs">Pending</span>}
                </td>
                <td className="px-4 py-3"><Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge></td>
                <td className="px-4 py-3"><Button variant="secondary" size="sm" onClick={() => onReviewClaim(claim.id)}>Review →</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );

  if (showTableOnly) {
    return <div className="space-y-4">{claimsTable}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-4">
        {[
          { label: 'Total Claims', value: String(claims.length), icon: <FileText size={15} />, color: 'blue' as const },
          { label: 'Verified', value: String(claims.filter(c => c.status === 'assessment_completed' || c.status === 'approved').length), icon: <CheckCircle size={15} />, color: 'green' as const },
          { label: 'Pending Review', value: String(pending), icon: <Clock size={15} />, color: 'amber' as const },
          { label: 'Approved', value: String(approved), icon: <ThumbsUp size={15} />, color: 'green' as const },
          { label: 'Rejected', value: String(rejected), icon: <XCircle size={15} />, color: 'red' as const },
          { label: 'Relief Disbursed', value: String(claims.filter(c => c.status === 'approved').length), icon: <CreditCard size={15} />, color: 'purple' as const },
        ].map(k => <KpiCard key={k.label} {...k} />)}
      </div>

      <div className="grid grid-cols-3 gap-5">
        <div className="col-span-2">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-[#e2e8f0]">
              <h2 className="text-sm font-semibold text-[#1a2130]">Tamil Nadu GIS Overview</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Total Claims: {claims.length}</span>
              </div>
            </div>
            <GISMap height={380} claims={claims} />
          </Card>
        </div>
        <div className="space-y-4">
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-[#1a2130] mb-3">Relief Payment Status</h3>
            <ReliefPaymentChart data={computePaymentStats(claims)} />
          </Card>
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-[#1a2130] mb-3">Claims Trend</h3>
            <MonthlyTrendChart data={computeClaimsOverTime(claims)} />
          </Card>
        </div>
      </div>

      {claimsTable}
    </div>
  );
}

// ── Main Portal ───────────────────────────────────────────────────────────
export function GovPortal({ user, onLogout }: GovPortalProps) {
  const [activeNav, setActiveNav] = useState('dashboard');
  const [reviewingClaim, setReviewingClaim] = useState<string | null>(null);
  const { claims, loading } = useClaims();

  const handleNavChange = (id: string) => {
    setActiveNav(id);
    setReviewingClaim(null);
  };

  if (loading) {
    return (
      <AppLayout role="government" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout} pageTitle="Government Officer Dashboard">
        <div className="flex items-center justify-center py-20">
          <Loader2 className="animate-spin text-[#156235]" size={32} />
          <span className="ml-3 text-slate-500">Loading real data…</span>
        </div>
      </AppLayout>
    );
  }

  const getContent = () => {
    if (reviewingClaim) {
      const claim = claims.find(c => c.id === reviewingClaim) ?? claims[0];
      if (!claim) return <div className="text-center text-slate-400 py-10">No claim found</div>;
      return <ClaimReviewWorkspace claim={claim} onBack={() => setReviewingClaim(null)} onDecision={() => {}} />;
    }
    if (activeNav === 'analytics') return <AnalyticsScreen claims={claims} />;
    if (activeNav === 'verified-claims') return <GovDashboard claims={claims} onReviewClaim={(id) => setReviewingClaim(id)} showTableOnly />;
    return <GovDashboard claims={claims} onReviewClaim={(id) => setReviewingClaim(id)} />;
  };

  const getTitle = () => {
    if (reviewingClaim) return undefined;
    if (activeNav === 'dashboard') return 'Government Officer Dashboard';
    if (activeNav === 'analytics') return 'District Analytics';
    if (activeNav === 'verified-claims') return 'Verified Claims';
    return undefined;
  };

  return (
    <AppLayout role="government" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout} pageTitle={getTitle()}>
      {getContent()}
    </AppLayout>
  );
}
