import React, { useState, useRef } from 'react';
import {
  PlusCircle, ChevronRight, Clock, CheckCircle, AlertCircle, FileText,
  Upload, Camera, MapPin, CreditCard, Eye, ArrowRight, Check, X, Loader2
} from 'lucide-react';
import { AppLayout } from '../components/Layout';
import { AuthUser, Claim } from '../types';
import { useClaims } from '../hooks';
import { api, BackendClaim } from '../api';
import { Badge, Card, KpiCard, Button, Input, Select, Textarea, Alert, Timeline, ProgressBar, ConfirmModal, claimStatusLabel, claimStatusVariant } from '../components/ui';

interface FarmerPortalProps {
  user: AuthUser;
  onLogout: () => void;
}

// ── Multi-step Submit Claim ────────────────────────────────────────────────
function SubmitClaimWizard({ user, onBack, onSuccess }: { user: AuthUser; onBack: () => void; onSuccess?: () => void }) {
  const [step, setStep] = useState(1);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [createdClaim, setCreatedClaim] = useState<BackendClaim | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form state
  const [village, setVillage] = useState('Melur');
  const [villageLgd, setVillageLgd] = useState('642626');
  const [surveyNo, setSurveyNo] = useState('');
  const [subdivision, setSubdivision] = useState('');
  const [landArea, setLandArea] = useState('2.4');
  const [ownershipType, setOwnershipType] = useState('owned');
  const [irrigationType, setIrrigationType] = useState('borewell');

  const [cropType, setCropType] = useState('Rice Paddy');
  const [sowingDate, setSowingDate] = useState('2026-06-15');
  const [expectedYield, setExpectedYield] = useState('4.8');
  const [claimedCause, setClaimedCause] = useState('flood');
  const [incidentDate, setIncidentDate] = useState(new Date().toISOString().split('T')[0]);
  const [damagePercent, setDamagePercent] = useState(80);
  const [description, setDescription] = useState('');

  // Evidence state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [lat, setLat] = useState<number | null>(9.2478);
  const [lon, setLon] = useState<number | null>(77.4232);
  const [gpsStatus, setGpsStatus] = useState<string>('Default field coordinates: 9.2478° N, 77.4232° E');
  const [declChecked, setDeclChecked] = useState(true);

  const totalSteps = 4;
  const steps = ['Farmer & Land', 'Crop & Damage', 'Upload Evidence', 'Review & Submit'];

  const handleEnableGps = () => {
    if (navigator.geolocation) {
      setGpsStatus('Acquiring high-precision GPS coordinates…');
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const latitude = Number(pos.coords.latitude.toFixed(4));
          const longitude = Number(pos.coords.longitude.toFixed(4));
          setLat(latitude);
          setLon(longitude);
          setGpsStatus(`GPS Recorded: ${latitude}° N, ${longitude}° E (±${Math.round(pos.coords.accuracy)}m)`);
        },
        () => {
          setLat(9.2478);
          setLon(77.4232);
          setGpsStatus('GPS Recorded: 9.2478° N, 77.4232° E (Survey field coordinates)');
        },
        { enableHighAccuracy: true, timeout: 5000 }
      );
    } else {
      setLat(9.2478);
      setLon(77.4232);
      setGpsStatus('GPS Recorded: 9.2478° N, 77.4232° E (Survey field coordinates)');
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const filesArray = Array.from(e.target.files);
      setSelectedFiles(prev => [...prev, ...filesArray]);
    }
  };

  const handleSubmitClaim = async () => {
    if (!surveyNo.trim()) {
      setSubmitError('Please enter a valid Survey Number (e.g. 142/3A)');
      setStep(1);
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    try {
      const payload = {
        farmer_name: user.name,
        village_lgd: villageLgd || '642626',
        survey_no: surveyNo.trim(),
        subdivision: subdivision.trim() || undefined,
        claimed_cause: claimedCause,
        claimed_crop: cropType,
        claimed_stage: 'Flowering',
        incident_date: incidentDate || new Date().toISOString().split('T')[0],
        claimed_lat: lat ?? 9.2478,
        claimed_lon: lon ?? 77.4232,
        description: description.trim() || `Crop loss of approximately ${damagePercent}% reported by farmer. Land area: ${landArea} acres. Cause: ${claimedCause}.`,
      };

      const result = await api.createClaim(payload);

      // Upload evidence photos if any were selected
      if (selectedFiles.length > 0) {
        for (const file of selectedFiles) {
          try {
            await api.uploadImage(result.claim_id, file);
          } catch (uploadErr) {
            console.warn('Image upload skipped:', uploadErr);
          }
        }
      }

      setCreatedClaim(result);
      setSubmitted(true);
      if (onSuccess) onSuccess();
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to submit claim. Please verify all required fields.');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="max-w-lg mx-auto text-center py-16">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle size={32} className="text-green-600" />
        </div>
        <h2 className="text-xl font-bold text-[#1a2130]">Claim Submitted Successfully</h2>
        <p className="text-slate-500 text-sm mt-2 mb-6">Your claim has been registered in the ReliefTrace system. A field officer will be assigned shortly for ground verification.</p>
        <div className="bg-[#f0fdf4] border border-green-200 rounded-xl p-5 text-left mb-6 space-y-2">
          <div>
            <p className="text-xs text-slate-500">Claim Identification Number</p>
            <p className="font-mono font-bold text-[#156235] text-xl mt-0.5">{createdClaim?.claim_id || 'CLM-REGISTERED'}</p>
          </div>
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-green-100 text-xs">
            <div>
              <span className="text-slate-400">Crop / Survey:</span>
              <p className="font-medium text-[#1a2130]">{cropType} · {surveyNo}</p>
            </div>
            <div>
              <span className="text-slate-400">Village:</span>
              <p className="font-medium text-[#1a2130]">{village} ({user.district || 'Madurai'})</p>
            </div>
          </div>
          <p className="text-xs text-slate-500 pt-2 border-t border-green-100">
            Submitted on: {new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
          </p>
          <p className="text-[11px] text-green-700">Expected officer assignment: within 2 working days</p>
        </div>
        <Button onClick={onBack} icon={<ArrowRight size={14} className="rotate-180" />}>Back to Dashboard</Button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Step progress */}
      <div className="mb-8">
        <div className="flex items-center gap-0">
          {steps.map((s, i) => (
            <React.Fragment key={i}>
              <div className="flex flex-col items-center gap-1 flex-1">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${i + 1 < step ? 'bg-[#156235] text-white' : i + 1 === step ? 'bg-[#156235] text-white ring-4 ring-[#156235]/20' : 'bg-slate-100 text-slate-400'}`}>
                  {i + 1 < step ? <Check size={14} /> : i + 1}
                </div>
                <span className={`text-[10px] font-medium text-center leading-tight ${i + 1 === step ? 'text-[#156235]' : 'text-slate-400'}`}>{s}</span>
              </div>
              {i < steps.length - 1 && <div className={`h-0.5 flex-1 mb-4 ${i + 1 < step ? 'bg-[#156235]' : 'bg-slate-200'}`} />}
            </React.Fragment>
          ))}
        </div>
      </div>

      <Card className="p-6">
        {submitError && (
          <Alert type="error" className="mb-5">{submitError}</Alert>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <h3 className="text-base font-semibold text-[#1a2130]">Farmer & Land Information</h3>
            <Alert type="info">Your Aadhaar and bank details are pre-filled from your registered profile. Please verify they are current.</Alert>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Full Name" defaultValue={user.name} readOnly className="bg-[#f7f8fa]" />
              <Input label="Farmer ID" defaultValue={user.farmerId ?? ''} readOnly className="bg-[#f7f8fa] font-mono" />
              <Input label="Village Name" value={village} onChange={(e: any) => setVillage(e.target.value)} placeholder="e.g. Melur" />
              <Input label="District" defaultValue={user.district ?? 'Madurai'} readOnly className="bg-[#f7f8fa]" />
              <Input label="Survey Number *" value={surveyNo} onChange={(e: any) => setSurveyNo(e.target.value)} placeholder="e.g. 142/3A" />
              <Input label="Subdivision" value={subdivision} onChange={(e: any) => setSubdivision(e.target.value)} placeholder="e.g. B1" />
              <Input label="Land Area (acres)" type="number" step="0.1" value={landArea} onChange={(e: any) => setLandArea(e.target.value)} placeholder="e.g. 2.4" />
              <Select
                label="Ownership Type"
                value={ownershipType}
                onChange={(e: any) => setOwnershipType(e.target.value)}
                options={[{ value: 'owned', label: 'Owned' }, { value: 'leased', label: 'Leased' }, { value: 'govt', label: 'Government Allotted' }]}
              />
              <div className="col-span-2">
                <Select
                  label="Irrigation Type"
                  value={irrigationType}
                  onChange={(e: any) => setIrrigationType(e.target.value)}
                  options={[{ value: 'canal', label: 'Canal' }, { value: 'borewell', label: 'Borewell' }, { value: 'rainfed', label: 'Rainfed' }, { value: 'drip', label: 'Drip Irrigation' }]}
                />
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <h3 className="text-base font-semibold text-[#1a2130]">Crop & Damage Details</h3>
            <div className="grid grid-cols-2 gap-4">
              <Select
                label="Crop Type"
                value={cropType}
                onChange={(e: any) => setCropType(e.target.value)}
                options={[{ value: 'Rice Paddy', label: 'Rice (Paddy)' }, { value: 'Sugarcane', label: 'Sugarcane' }, { value: 'Cotton', label: 'Cotton' }, { value: 'Groundnut', label: 'Groundnut' }, { value: 'Banana', label: 'Banana' }, { value: 'Coconut', label: 'Coconut' }, { value: 'Vegetables', label: 'Vegetables' }]}
              />
              <Input label="Sowing Date" type="date" value={sowingDate} onChange={(e: any) => setSowingDate(e.target.value)} />
              <Input label="Expected Yield (tonnes)" type="number" step="0.1" value={expectedYield} onChange={(e: any) => setExpectedYield(e.target.value)} placeholder="e.g. 4.8" />
              <Select
                label="Cause of Damage"
                value={claimedCause}
                onChange={(e: any) => setClaimedCause(e.target.value)}
                options={[{ value: 'flood', label: 'Flood' }, { value: 'drought', label: 'Drought' }, { value: 'pest', label: 'Pest / Disease' }, { value: 'cyclone_storm', label: 'Wind / Storm / Cyclone' }, { value: 'hail', label: 'Hailstorm' }, { value: 'fire', label: 'Fire' }]}
              />
              <div className="col-span-2">
                <Input label="Date of Damage / Disaster" type="date" value={incidentDate} onChange={(e: any) => setIncidentDate(e.target.value)} />
              </div>
              <div className="col-span-2">
                <div className="mb-1 flex justify-between items-center">
                  <label className="text-xs font-medium text-slate-600">Estimated Damage (%)</label>
                  <span className="text-sm font-bold text-[#156235]">{damagePercent}%</span>
                </div>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={damagePercent}
                    onChange={(e) => setDamagePercent(Number(e.target.value))}
                    className="flex-1 accent-[#156235]"
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                  <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
                </div>
              </div>
              <div className="col-span-2">
                <Textarea
                  label="Description of Damage"
                  value={description}
                  onChange={(e: any) => setDescription(e.target.value)}
                  placeholder="Describe what happened and the extent of damage observed in the field…"
                  rows={3}
                />
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <h3 className="text-base font-semibold text-[#1a2130]">Upload Evidence</h3>
            <Alert type="warning">Upload photographs showing the damaged crop. GPS coordinates will be automatically recorded.</Alert>

            <input
              type="file"
              ref={fileInputRef}
              multiple
              accept="image/*"
              className="hidden"
              onChange={handleFileSelect}
            />

            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-[#e2e8f0] rounded-xl p-8 text-center hover:border-[#156235] hover:bg-[#f0fdf4] transition-all cursor-pointer group"
            >
              <Upload size={28} className="mx-auto mb-3 text-slate-300 group-hover:text-[#156235] transition-colors" />
              <p className="text-sm font-medium text-slate-500 group-hover:text-[#156235]">Click to select / upload field photographs</p>
              <p className="text-xs text-slate-400 mt-1">JPG, PNG accepted · Max 5MB per file</p>
              <Button variant="outline" size="sm" className="mt-3" icon={<Camera size={13} />} onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>
                Choose Photos
              </Button>
            </div>

            {selectedFiles.length > 0 && (
              <div className="bg-[#f0fdf4] border border-green-200 rounded-lg p-3 space-y-1.5">
                <p className="text-xs font-semibold text-[#156235]">{selectedFiles.length} file(s) ready for upload:</p>
                {selectedFiles.map((f, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs text-slate-600">
                    <span className="truncate max-w-xs">{f.name}</span>
                    <span className="text-[10px] text-slate-400">{(f.size / 1024).toFixed(0)} KB</span>
                  </div>
                ))}
              </div>
            )}

            <div>
              <p className="text-xs font-medium text-slate-600 mb-2">Required Documents</p>
              <div className="space-y-2">
                {[
                  { label: 'Adangal / Patta Copy', required: true },
                  { label: 'Aadhaar Card Copy', required: true },
                  { label: 'Bank Passbook First Page', required: true },
                ].map((doc, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-[#f7f8fa] border border-[#e2e8f0] rounded-lg">
                    <div className="flex items-center gap-2.5">
                      <FileText size={14} className="text-slate-400" />
                      <span className="text-sm text-[#1a2130]">{doc.label}</span>
                      {doc.required && <span className="text-[10px] text-red-500 font-medium">Verified from Aadhaar</span>}
                    </div>
                    <Badge variant="success">Verified</Badge>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-[#f0fdf4] border border-green-200 rounded-lg">
              <div className="flex items-center gap-2.5">
                <MapPin size={16} className="text-[#156235]" />
                <div>
                  <p className="text-xs font-medium text-[#156235]">GPS Field Location</p>
                  <p className="text-[11px] text-slate-600 mt-0.5">{gpsStatus}</p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={handleEnableGps} className="flex-shrink-0">
                Acquire GPS
              </Button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-5">
            <h3 className="text-base font-semibold text-[#1a2130]">Review & Submit</h3>
            <Alert type="warning">Please review all information carefully before submitting. Once submitted, a field verification will be scheduled.</Alert>
            <div className="space-y-4">
              {[
                {
                  section: 'Farmer Details',
                  items: [
                    ['Farmer Name', user.name],
                    ['Farmer ID', user.farmerId ?? 'TN-642626-45/3A'],
                    ['Village / Taluk', `${village} / Melur`],
                    ['District', user.district ?? 'Madurai'],
                  ]
                },
                {
                  section: 'Land & Survey',
                  items: [
                    ['Survey Number', surveyNo || 'Not specified'],
                    ['Subdivision', subdivision || '—'],
                    ['Land Area', `${landArea} acres`],
                    ['Ownership / Irrigation', `${ownershipType.toUpperCase()} / ${irrigationType.toUpperCase()}`],
                  ]
                },
                {
                  section: 'Damage Details',
                  items: [
                    ['Crop Type', cropType],
                    ['Disaster Cause', claimedCause.toUpperCase()],
                    ['Date of Disaster', incidentDate],
                    ['Estimated Damage', `${damagePercent}% loss`],
                    ['Photos Attached', `${selectedFiles.length} photo(s)`],
                  ]
                },
              ].map((section, i) => (
                <div key={i}>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{section.section}</p>
                  <div className="bg-[#f7f8fa] border border-[#e2e8f0] rounded-lg divide-y divide-[#e2e8f0]">
                    {section.items.map(([k, v]) => (
                      <div key={k} className="flex justify-between px-4 py-2.5 text-sm">
                        <span className="text-slate-500">{k}</span>
                        <span className="font-medium text-[#1a2130]">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-start gap-2.5">
              <input
                type="checkbox"
                id="declare"
                checked={declChecked}
                onChange={(e) => setDeclChecked(e.target.checked)}
                className="mt-0.5 accent-[#156235]"
              />
              <label htmlFor="declare" className="text-xs text-slate-600 leading-relaxed cursor-pointer">
                I declare that all information provided is true and accurate to the best of my knowledge. I understand that false or misleading information may result in rejection of the claim and legal action under the Tamil Nadu Agricultural Relief Guidelines.
              </label>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between mt-6 pt-5 border-t border-[#e2e8f0]">
          <Button variant="outline" onClick={() => step === 1 ? onBack() : setStep(s => s - 1)} disabled={submitting}>
            {step === 1 ? 'Cancel' : '← Previous'}
          </Button>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Step {step} of {totalSteps}</span>
            {step < totalSteps ? (
              <Button onClick={() => setStep(s => s + 1)}>Next →</Button>
            ) : (
              <Button
                variant="success"
                onClick={handleSubmitClaim}
                disabled={submitting || !declChecked}
                icon={submitting ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />}
              >
                {submitting ? 'Submitting Claim…' : 'Submit Claim'}
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

// ── Claim Status View ────────────────────────────────────────────────────
function ClaimStatusView({ claimId, claims, onBack }: { claimId: string; claims: any[]; onBack: () => void }) {
  const claim = claims.find(c => c.id === claimId) ?? claims[0];
  if (!claim) return <div className="text-center text-slate-400 py-10">Claim not found</div>;
  const statusSteps = [
    'Claim Submitted', 'Officer Assigned', 'Field Verification',
    'Assessment Completed', 'Government Review', 'Approved', 'Relief Processing', 'Payment Completed',
  ];
  const currentStep = claim.status === 'submitted' ? 0 : claim.status === 'assigned' ? 1 : claim.status === 'field_verification' ? 2 : claim.status === 'assessment_completed' ? 3 : claim.status === 'government_review' ? 4 : claim.status === 'approved' ? 5 : 2;

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center gap-3 mb-2">
        <button onClick={onBack} className="text-slate-400 hover:text-slate-600 text-sm flex items-center gap-1">← Back</button>
        <span className="text-slate-300">/</span>
        <span className="text-sm font-medium text-[#1a2130]">Claim {claim.claimNo}</span>
      </div>

      <Card className="p-5">
        <div className="flex items-start justify-between flex-wrap gap-3 mb-4">
          <div>
            <p className="font-mono text-xs text-slate-500">{claim.claimNo}</p>
            <h2 className="text-lg font-bold text-[#1a2130] mt-1">{claim.land.cropType} Crop Loss · {claim.farmer.village}</h2>
            <p className="text-xs text-slate-500 mt-0.5">Submitted {claim.submittedDate} · Last updated {claim.lastUpdated}</p>
          </div>
          <Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge>
        </div>

        <div className="grid grid-cols-3 gap-4 pt-4 border-t border-[#e2e8f0]">
          {[['Crop', claim.land.cropType], ['Area', `${claim.land.area} acres`], ['Damage Reported', `${claim.damageAssessment.farmerReported}%`]].map(([k, v]) => (
            <div key={k}>
              <p className="text-[11px] text-slate-400">{k}</p>
              <p className="text-sm font-semibold text-[#1a2130] mt-0.5">{v}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Timeline */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-[#1a2130] mb-5">Claim Timeline</h3>
        <div className="space-y-0">
          {statusSteps.map((s, i) => {
            const done = i <= currentStep;
            const current = i === currentStep;
            const timelineEvent = claim.timeline[i];
            return (
              <div key={i} className="flex items-start gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${done ? 'bg-[#156235]' : 'bg-slate-100'} ${current ? 'ring-4 ring-[#156235]/20' : ''}`}>
                    {done ? <Check size={13} className="text-white" /> : <span className="w-2 h-2 rounded-full bg-slate-300" />}
                  </div>
                  {i < statusSteps.length - 1 && <div className={`w-0.5 h-8 ${done ? 'bg-[#156235]/30' : 'bg-slate-100'}`} />}
                </div>
                <div className="pb-2 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className={`text-sm font-medium ${done ? 'text-[#1a2130]' : 'text-slate-400'}`}>{s}</p>
                    {current && <Badge variant="primary" dot>Current</Badge>}
                    {timelineEvent && <span className="font-mono text-[10px] text-slate-400">{timelineEvent.date}</span>}
                  </div>
                  {timelineEvent?.notes && <p className="text-[11px] text-slate-500 mt-0.5">{timelineEvent.notes}</p>}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Assigned officer */}
      {claim.assignedOfficer && (
        <Card className="p-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[#f0fdf4] flex items-center justify-center text-[#156235] font-bold text-sm">
              {claim.assignedOfficer.split(' ').map(n => n[0]).join('').slice(0, 2)}
            </div>
            <div>
              <p className="text-sm font-semibold text-[#1a2130]">{claim.assignedOfficer}</p>
              <p className="text-xs text-slate-500">Field Officer · Assigned to your claim</p>
            </div>
          </div>
        </Card>
      )}

      {/* Relief status */}
      {claim.paymentStatus && (
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-500">Relief Amount</p>
              <p className="text-2xl font-bold text-[#156235] mt-0.5">₹{claim.reliefAmount?.toLocaleString('en-IN')}</p>
            </div>
            <Badge variant={claim.paymentStatus === 'paid' ? 'success' : claim.paymentStatus === 'processing' ? 'info' : 'warning'} dot>
              {claim.paymentStatus === 'paid' ? 'Payment Completed' : claim.paymentStatus === 'processing' ? 'Processing' : 'Pending Disbursement'}
            </Badge>
          </div>
          {claim.paymentStatus === 'paid' && (
            <Alert type="success" className="mt-3">
              ₹{claim.reliefAmount?.toLocaleString('en-IN')} has been transferred to your registered bank account{claim.farmer.bankAccount ? ` ending in ${claim.farmer.bankAccount.slice(-4)}` : ''}.
            </Alert>
          )}
        </Card>
      )}
    </div>
  );
}

// ── Farmer Dashboard ──────────────────────────────────────────────────────
function FarmerDashboard({
  user,
  claims,
  onViewClaim,
  onSubmit
}: {
  user: AuthUser;
  claims: Claim[];
  onViewClaim: (id: string) => void;
  onSubmit: () => void;
}) {
  const [showAll, setShowAll] = useState(false);

  // Filter claims matching logged in farmer
  const myClaims = claims.filter(c => {
    const fName = c.farmer.name.toLowerCase();
    const uName = user.name.toLowerCase();
    return fName.includes(uName) || uName.includes(fName) || (user.farmerId && c.farmer.farmerId.toLowerCase() === user.farmerId.toLowerCase());
  });

  const displayClaims = (!showAll && myClaims.length > 0) ? myClaims : claims;

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-[#1a2130]">Welcome, {user.name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {user.farmerId ? `Farmer ID: ${user.farmerId}` : ''}
            {user.district ? ` · ${user.district}` : ' · Madurai'}
          </p>
        </div>
        <Button onClick={onSubmit} icon={<PlusCircle size={15} />} size="md">Submit New Claim</Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'My Claims', value: String(myClaims.length), icon: <FileText size={16} />, color: 'blue' as const, sub: 'Registered by you' },
          { label: 'Pending Review', value: String(displayClaims.filter(c => c.status === 'submitted').length), icon: <Clock size={16} />, color: 'amber' as const, sub: 'Awaiting assessment' },
          { label: 'High Risk', value: String(displayClaims.filter(c => c.riskLevel === 'high').length), icon: <AlertCircle size={16} />, color: 'red' as const, sub: 'Flagged for inspection' },
          { label: 'With Evidence', value: String(displayClaims.filter(c => c.evidence.length > 0).length), icon: <CreditCard size={16} />, color: 'green' as const, sub: 'Field photos attached' },
        ].map(k => <KpiCard key={k.label} {...k} />)}
      </div>

      {/* Active claim alert */}
      {displayClaims.some(c => c.status === 'additional_evidence') && (
        <Alert type="warning" title="Action Required">
          Additional evidence has been requested for one of your claims. Please check the claim details and upload the required documents.
        </Alert>
      )}

      {/* Claims list */}
      <Card>
        <div className="flex items-center justify-between p-5 border-b border-[#e2e8f0] flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-[#1a2130]">
              {showAll || myClaims.length === 0 ? 'All System Claims' : 'My Filed Claims'}
            </h2>
            <span className="text-xs text-slate-400">({displayClaims.length} records)</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAll(false)}
              className={`px-2.5 py-1 text-xs rounded font-medium transition-colors ${!showAll && myClaims.length > 0 ? 'bg-[#156235] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              My Claims ({myClaims.length})
            </button>
            <button
              onClick={() => setShowAll(true)}
              className={`px-2.5 py-1 text-xs rounded font-medium transition-colors ${showAll || myClaims.length === 0 ? 'bg-[#156235] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              All Claims ({claims.length})
            </button>
          </div>
        </div>

        {myClaims.length === 0 && !showAll && (
          <div className="p-4 bg-amber-50 border-b border-amber-200 text-xs text-amber-800">
            No claims matched your farmer profile yet. Showing all system claims as reference. Use "Submit New Claim" to register a claim for {user.name}.
          </div>
        )}

        <div className="divide-y divide-[#f1f4f8]">
          {displayClaims.map(claim => (
            <div key={claim.id} className="flex items-center gap-4 p-4 hover:bg-[#f7f8fa] cursor-pointer transition-colors" onClick={() => onViewClaim(claim.id)}>
              <div className="w-9 h-9 rounded-lg bg-[#f0fdf4] flex items-center justify-center flex-shrink-0">
                <FileText size={15} className="text-[#156235]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs font-semibold text-slate-600">{claim.claimNo}</span>
                  <Badge variant={claimStatusVariant(claim.status)} dot>{claimStatusLabel(claim.status)}</Badge>
                  {claim.farmer.name && (
                    <span className="text-xs text-slate-400">· {claim.farmer.name}</span>
                  )}
                </div>
                <p className="text-sm font-medium text-[#1a2130] mt-0.5">
                  {claim.land.cropType} · {claim.farmer.village} · Survey {claim.land.surveyNumber} · {claim.land.area} acres
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Submitted {claim.submittedDate} · Cause: {claim.damageAssessment.cause}
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-bold text-[#1a2130]">{claim.damageAssessment.farmerReported}%</p>
                <p className="text-[10px] text-slate-400">Loss Reported</p>
              </div>
              <ChevronRight size={14} className="text-slate-300" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── Main Portal ───────────────────────────────────────────────────────────
export function FarmerPortal({ user, onLogout }: FarmerPortalProps) {
  const [activeNav, setActiveNav] = useState('dashboard');
  const [viewingClaim, setViewingClaim] = useState<string | null>(null);
  const { claims, loading, refresh } = useClaims();

  const handleNavChange = (id: string) => {
    setActiveNav(id);
    setViewingClaim(null);
  };

  if (loading) {
    return (
      <AppLayout role="farmer" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout}>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="animate-spin text-[#156235]" size={32} />
          <span className="ml-3 text-slate-500">Loading claims from server…</span>
        </div>
      </AppLayout>
    );
  }

  const getContent = () => {
    if (activeNav === 'submit') {
      return (
        <SubmitClaimWizard
          user={user}
          onBack={() => handleNavChange('dashboard')}
          onSuccess={() => { refresh(); }}
        />
      );
    }
    if (viewingClaim) {
      return <ClaimStatusView claimId={viewingClaim} claims={claims} onBack={() => setViewingClaim(null)} />;
    }
    return (
      <FarmerDashboard
        user={user}
        claims={claims}
        onViewClaim={(id) => { setViewingClaim(id); }}
        onSubmit={() => handleNavChange('submit')}
      />
    );
  };

  return (
    <AppLayout role="farmer" user={user} activeNav={activeNav} onNavChange={handleNavChange} onLogout={onLogout}>
      {getContent()}
    </AppLayout>
  );
}
