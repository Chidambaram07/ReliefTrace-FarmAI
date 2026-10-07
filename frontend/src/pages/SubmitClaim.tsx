import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type BackendClaim, type BackendImage } from '../api';
import {
  Upload, Link2, CheckCircle, AlertTriangle, Info, MapPin, Calendar,
  Hash, Ruler, Eye, ArrowRight,
} from 'lucide-react';

const CAUSES = ['drought', 'flood', 'cyclone_storm', 'hail', 'pest', 'disease', 'fire', 'other'];
const STAGES = ['bare_soil_or_fallow', 'sown', 'vegetation', 'flowering', 'full_growth', 'harvesting'];

const INITIAL = {
  farmer_name: '', village_lgd: '', survey_no: '', subdivision: '',
  claimed_cause: 'flood', claimed_crop: '', claimed_stage: '',
  incident_date: '', claimed_lat: '', claimed_lon: '', description: '',
};

function Label({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
      {children}{required && <span style={{ color: '#dc2626', marginLeft: 3 }}>*</span>}
    </label>
  );
}

function Field({ children, span = 1 }: { children: React.ReactNode; span?: number }) {
  return <div style={{ gridColumn: `span ${span}` }}>{children}</div>;
}

function Input({
  value, onChange, placeholder, type = 'text', required,
}: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; required?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      required={required}
      placeholder={placeholder}
      onChange={e => onChange(e.target.value)}
      style={{
        width: '100%', padding: '8px 10px', fontSize: 13, border: '1px solid #d1d5db',
        borderRadius: 6, outline: 'none', fontFamily: 'inherit', background: 'white',
        boxSizing: 'border-box',
      }}
    />
  );
}

function Sel({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        width: '100%', padding: '8px 10px', fontSize: 13, border: '1px solid #d1d5db',
        borderRadius: 6, outline: 'none', fontFamily: 'inherit', background: 'white',
      }}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function ImageCard({ img, claimId }: { img: BackendImage; claimId: string }) {
  return (
    <div style={{
      border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden',
      background: 'white',
    }}>
      {img.file_available ? (
        <img
          src={api.imageFileUrl(claimId, img.image_key)}
          alt={img.filename || 'attached image'}
          style={{ width: '100%', height: 160, objectFit: 'cover', display: 'block', background: '#f1f5f9' }}
          onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
        />
      ) : (
        <div style={{
          height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#f8fafc', color: '#94a3b8', fontSize: 12, flexDirection: 'column', gap: 6,
        }}>
          <Eye size={24} />
          <span>File not on disk</span>
        </div>
      )}
      <div style={{ padding: '10px 12px' }}>
        <div style={{
          display: 'inline-block', fontSize: 10, fontWeight: 700, padding: '2px 7px',
          borderRadius: 4, marginBottom: 6,
          background: img.source === 'dataset' ? '#ede9fe' : '#f0f9ff',
          color: img.source === 'dataset' ? '#7c3aed' : '#0369a1',
        }}>
          {img.source === 'dataset' ? 'Dataset Image' : 'Uploaded Photo'}
        </div>
        <div style={{ fontSize: 11, color: '#374151', marginBottom: 2 }}>
          <strong>{img.filename || '(unnamed)'}</strong>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {img.sha256 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#64748b' }}>
              <Hash size={10} />
              <code style={{ fontFamily: 'DM Mono, monospace' }}>{img.sha256.slice(0, 16)}…</code>
            </div>
          )}
          {img.width && img.height && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#64748b' }}>
              <Ruler size={10} /> {img.width} × {img.height} px
            </div>
          )}
          {img.size_bytes && (
            <div style={{ fontSize: 10, color: '#94a3b8' }}>
              {(img.size_bytes / 1024).toFixed(1)} KB
            </div>
          )}
          {img.exif?.gps_lat != null && img.exif?.gps_lon != null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#059669' }}>
              <MapPin size={10} />
              EXIF GPS: {img.exif.gps_lat.toFixed(4)}°N, {img.exif.gps_lon.toFixed(4)}°E
            </div>
          )}
          {img.exif?.captured_at && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#64748b' }}>
              <Calendar size={10} /> EXIF: {img.exif.captured_at}
            </div>
          )}
          {img.dataset_image_id && (
            <div style={{ fontSize: 10, color: '#7c3aed', marginTop: 2 }}>
              Dataset ID: {img.dataset_image_id.slice(0, 20)}…
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, marginTop: 2 }}>
            {img.file_available ? (
              <><CheckCircle size={10} color="#16a34a" /><span style={{ color: '#16a34a' }}>File available</span></>
            ) : (
              <><AlertTriangle size={10} color="#ea580c" /><span style={{ color: '#ea580c' }}>File not on disk</span></>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function BannerErr({ msg }: { msg: string }) {
  return (
    <div style={{
      background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6,
      padding: '10px 14px', fontSize: 13, color: '#dc2626',
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <AlertTriangle size={14} /> {msg}
    </div>
  );
}

export function SubmitClaim() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState(INITIAL);
  const [claim, setClaim] = useState<BackendClaim | null>(null);
  const [images, setImages] = useState<BackendImage[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [investigationStarted, setInvestigationStarted] = useState(false);

  const set = (k: keyof typeof INITIAL) => (v: string) => setForm(f => ({ ...f, [k]: v }));

  async function submitClaim(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const body: any = { ...form };
      for (const k of Object.keys(body)) if (body[k] === '') body[k] = null;
      if (body.claimed_lat != null) body.claimed_lat = parseFloat(body.claimed_lat);
      if (body.claimed_lon != null) body.claimed_lon = parseFloat(body.claimed_lon);
      if (isNaN(body.claimed_lat)) body.claimed_lat = null;
      if (isNaN(body.claimed_lon)) body.claimed_lon = null;
      const c = await api.createClaim(body);
      setClaim(c);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !claim) return;
    setBusy(true);
    setError(null);
    try {
      const img = await api.uploadImage(claim.claim_id, file);
      setImages(prev => [...prev, img]);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function attachDataset() {
    if (!datasetId.trim() || !claim) return;
    setBusy(true);
    setError(null);
    try {
      const img = await api.attachDatasetImage(claim.claim_id, datasetId.trim());
      setImages(prev => [...prev, img]);
      setDatasetId('');
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function startInvestigation() {
    if (!claim) return;
    setBusy(true);
    setError(null);
    setInvestigationStarted(true);
    try {
      // Fire agentic verification, then navigate to workspace
      await api.verifyAgentic(claim.claim_id);
      navigate(`/claims/${claim.claim_id}`);
    } catch (err: any) {
      // Even if agentic returns an error, navigate — the workspace will show the error
      const code = (err as any)?.code;
      if (code !== 'CLAIM_NOT_FOUND') {
        navigate(`/claims/${claim.claim_id}`);
      } else {
        setError(err?.message || String(err));
        setInvestigationStarted(false);
      }
    } finally {
      setBusy(false);
    }
  }

  // ── After claim created: evidence + investigation step ────────────────
  if (claim) {
    return (
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: '#0d1117', margin: 0 }}>
            Claim Recorded
          </h1>
          <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
            <code style={{ fontFamily: 'DM Mono, monospace', color: '#156235' }}>{claim.claim_id}</code>
            {' · '}This is the claimant's account only — not yet verified. Attach evidence below, then start investigation.
          </p>
        </div>

        {error && <div style={{ marginBottom: 12 }}><BannerErr msg={error} /></div>}

        {/* Claim summary */}
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '16px 20px', marginBottom: 16 }}>
          <div style={{
            fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase',
            letterSpacing: '0.08em', marginBottom: 8,
          }}>
            Claim Summary — Claimant-submitted; unverified
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px 16px', fontSize: 13 }}>
            <div><span style={{ color: '#94a3b8' }}>Cause: </span><strong>{claim.claim.claimed_cause}</strong></div>
            <div><span style={{ color: '#94a3b8' }}>Survey: </span><strong>{claim.claim.survey_no}</strong></div>
            <div><span style={{ color: '#94a3b8' }}>Incident: </span><strong>{claim.claim.incident_date}</strong></div>
            {claim.claim.claimed_crop && <div><span style={{ color: '#94a3b8' }}>Crop: </span>{claim.claim.claimed_crop}</div>}
            {claim.claim.village_lgd && <div><span style={{ color: '#94a3b8' }}>LGD: </span>{claim.claim.village_lgd}</div>}
            {claim.claim.farmer_name && <div><span style={{ color: '#94a3b8' }}>Name: </span>{claim.claim.farmer_name}</div>}
          </div>
          {claim.claim.description && (
            <p style={{ fontSize: 12, color: '#64748b', marginTop: 8, fontStyle: 'italic' }}>
              "{claim.claim.description}"
            </p>
          )}
        </div>

        {/* Attach evidence */}
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '16px 20px', marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#0d1117', marginBottom: 12 }}>
            Attach Evidence Photos
          </div>

          {/* Upload */}
          <div style={{ marginBottom: 10 }}>
            <Label>Upload a photo from device (JPEG / PNG)</Label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png"
                onChange={uploadFile}
                disabled={busy}
                style={{ flex: 1, fontSize: 13, padding: '7px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
              />
            </div>
          </div>

          {/* Dataset attach */}
          <div style={{ marginBottom: 4 }}>
            <Label>Or attach a challenge dataset image by ID</Label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={datasetId}
                onChange={e => setDatasetId(e.target.value)}
                placeholder="e.g. 00b38c78-...933533_266_58_"
                disabled={busy}
                style={{
                  flex: 1, padding: '7px 10px', fontSize: 13, border: '1px solid #d1d5db',
                  borderRadius: 6, fontFamily: 'DM Mono, monospace',
                }}
              />
              <button
                onClick={attachDataset}
                disabled={busy || !datasetId.trim()}
                style={{
                  padding: '7px 16px', fontSize: 13, borderRadius: 6,
                  border: '1px solid #d1d5db', background: 'white', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <Link2 size={13} /> Attach
              </button>
            </div>
          </div>
        </div>

        {/* Image cards */}
        {images.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
              Attached Evidence ({images.length})
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
              {images.map(img => (
                <ImageCard key={img.image_key} img={img} claimId={claim.claim_id} />
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            onClick={startInvestigation}
            disabled={busy || investigationStarted}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px',
              fontSize: 14, fontWeight: 600, borderRadius: 6, border: 'none',
              background: busy || investigationStarted ? '#94a3b8' : '#156235',
              color: 'white', cursor: busy ? 'wait' : 'pointer',
            }}
          >
            {busy && investigationStarted ? 'Starting investigation…' : (
              <><ArrowRight size={15} /> Start Investigation</>
            )}
          </button>
          <button
            onClick={() => { setClaim(null); setImages([]); setForm(INITIAL); setInvestigationStarted(false); }}
            disabled={busy}
            style={{
              padding: '10px 16px', fontSize: 13, borderRadius: 6,
              border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer',
            }}
          >
            Submit Another Claim
          </button>
          <div style={{ fontSize: 12, color: '#94a3b8', marginLeft: 4 }}>
            <Info size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
            Photos are optional but improve investigation accuracy
          </div>
        </div>
      </div>
    );
  }

  // ── Claim form ─────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: '#0d1117', margin: 0 }}>Submit a Relief Claim</h1>
        <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
          All information below is the claimant's account only. ReliefTrace will compare it against
          independent reference records, photo analysis, weather, and location evidence.
        </p>
      </div>

      {error && <div style={{ marginBottom: 12 }}><BannerErr msg={error} /></div>}

      <form
        onSubmit={submitClaim}
        style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '20px 24px' }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px 16px', marginBottom: 14 }}>
          <Field>
            <Label>Your name (optional)</Label>
            <Input value={form.farmer_name} onChange={set('farmer_name')} />
          </Field>
          <Field>
            <Label>Village LGD code (6 digits, optional)</Label>
            <Input value={form.village_lgd} onChange={set('village_lgd')} placeholder="e.g. 642626" />
          </Field>
          <Field>
            <Label required>Survey number</Label>
            <Input value={form.survey_no} onChange={set('survey_no')} required placeholder="e.g. 45/3A" />
          </Field>
          <Field>
            <Label>Subdivision (optional)</Label>
            <Input value={form.subdivision} onChange={set('subdivision')} placeholder="e.g. A" />
          </Field>
          <Field>
            <Label required>What happened?</Label>
            <Sel
              value={form.claimed_cause}
              onChange={set('claimed_cause')}
              options={CAUSES.map(c => ({ value: c, label: c.replace(/_/g, ' ') }))}
            />
          </Field>
          <Field>
            <Label required>Date it happened</Label>
            <Input type="date" value={form.incident_date} onChange={set('incident_date')} required />
          </Field>
          <Field>
            <Label>Crop (optional)</Label>
            <Input value={form.claimed_crop} onChange={set('claimed_crop')} placeholder="e.g. Rice (Paddy)" />
          </Field>
          <Field>
            <Label>Growth stage (optional)</Label>
            <Sel
              value={form.claimed_stage}
              onChange={set('claimed_stage')}
              options={[{ value: '', label: 'Not sure' }, ...STAGES.map(s => ({ value: s, label: s.replace(/_/g, ' ') }))]}
            />
          </Field>
          <Field>
            <Label>Latitude (optional)</Label>
            <Input value={form.claimed_lat} onChange={set('claimed_lat')} placeholder="e.g. 9.2478" />
          </Field>
          <Field>
            <Label>Longitude (optional)</Label>
            <Input value={form.claimed_lon} onChange={set('claimed_lon')} placeholder="e.g. 77.4232" />
          </Field>
        </div>

        <div style={{ marginBottom: 16 }}>
          <Label>Additional details (optional)</Label>
          <textarea
            value={form.description}
            onChange={e => set('description')(e.target.value)}
            placeholder="Describe what happened in your own words…"
            rows={3}
            style={{
              width: '100%', padding: '8px 10px', fontSize: 13, border: '1px solid #d1d5db',
              borderRadius: 6, outline: 'none', fontFamily: 'inherit', resize: 'vertical',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <button
          type="submit"
          disabled={busy}
          style={{
            padding: '10px 20px', fontSize: 14, fontWeight: 600, borderRadius: 6,
            border: 'none', background: busy ? '#94a3b8' : '#156235',
            color: 'white', cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {busy ? 'Recording…' : 'Record Claim'}
        </button>
      </form>
    </div>
  );
}
