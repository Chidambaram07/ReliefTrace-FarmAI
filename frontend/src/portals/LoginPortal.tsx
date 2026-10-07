import React, { useState } from 'react';
import { Sprout, ArrowRight, Eye, EyeOff, Shield, MapPin, CheckCircle } from 'lucide-react';
import { Portal } from '../types';
import { MOCK_USERS } from '../data';
import { Button, Input, Alert } from '../components/ui';

interface LoginPortalProps {
  onLogin: (portal: Portal) => void;
}

const PORTAL_OPTIONS = [
  {
    id: 'farmer' as Portal,
    label: 'Farmer Portal',
    description: 'Submit and track crop-loss claims',
    icon: <Sprout size={20} />,
    bg: 'bg-teal-50',
    border: 'border-teal-200 hover:border-teal-400',
    text: 'text-teal-700',
    accent: '#0d9488',
    demo: { id: 'U001', label: 'Ramesh Kumar', sub: 'Farmer ID: TN-MDU-23841' },
  },
  {
    id: 'officer' as Portal,
    label: 'Field Officer Portal',
    description: 'Verify claims and submit assessments',
    icon: <MapPin size={20} />,
    bg: 'bg-green-50',
    border: 'border-green-200 hover:border-green-500',
    text: 'text-[#156235]',
    accent: '#156235',
    demo: { id: 'U002', label: 'Priya Chandran', sub: 'Field Officer — Madurai' },
  },
  {
    id: 'government' as Portal,
    label: 'Government Officer',
    description: 'Review verified claims and approve relief',
    icon: <Shield size={20} />,
    bg: 'bg-blue-50',
    border: 'border-blue-200 hover:border-blue-500',
    text: 'text-[#1e40af]',
    accent: '#1e40af',
    demo: { id: 'U003', label: 'V. Sureshkumar', sub: 'Deputy Director, Agriculture' },
  },
  {
    id: 'admin' as Portal,
    label: 'Administrator',
    description: 'Manage users, districts and system settings',
    icon: <CheckCircle size={20} />,
    bg: 'bg-purple-50',
    border: 'border-purple-200 hover:border-purple-500',
    text: 'text-purple-700',
    accent: '#7c3aed',
    demo: { id: 'U004', label: 'Admin User', sub: 'System Administrator' },
  },
];

export function LoginPortal({ onLogin }: LoginPortalProps) {
  const [selected, setSelected] = useState<Portal | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const selectedPortal = PORTAL_OPTIONS.find(p => p.id === selected);

  const handleLogin = () => {
    if (!selected) return;
    setLoading(true);
    setError('');
    setTimeout(() => {
      setLoading(false);
      onLogin(selected);
    }, 900);
  };

  return (
    <div className="min-h-screen flex">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-[480px] bg-[#0d1117] flex-col justify-between p-10 flex-shrink-0">
        <div>
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 bg-[#156235] rounded-xl flex items-center justify-center">
              <Sprout size={20} className="text-white" />
            </div>
            <div>
              <p className="text-white font-bold text-xl leading-none">ReliefTrace</p>
              <p className="text-white/40 text-[11px] mt-0.5">Agricultural Claim Verification Platform</p>
            </div>
          </div>

          <h2 className="text-3xl font-bold text-white leading-tight mb-4">
            Verify claims.<br />Trace evidence.<br /><span className="text-[#16a34a]">Deliver relief.</span>
          </h2>
          <p className="text-white/50 text-sm leading-relaxed">
            A professional platform for evidence-based crop-loss claim verification and relief disbursement, used by field officers, government officials, and agricultural departments across Tamil Nadu.
          </p>
        </div>

        <div className="space-y-4">
          {[
            { icon: <MapPin size={15} />, label: 'GIS-verified field locations' },
            { icon: <CheckCircle size={15} />, label: 'AI-assisted damage assessment' },
            { icon: <Shield size={15} />, label: 'Risk and duplicate detection' },
            { icon: <Sprout size={15} />, label: 'Transparent relief tracking' },
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-3 text-white/60 text-sm">
              <span className="text-[#16a34a] flex-shrink-0">{item.icon}</span>
              {item.label}
            </div>
          ))}

          <div className="pt-4 border-t border-white/10">
            <p className="text-white/30 text-xs">Government of Tamil Nadu · Department of Agriculture</p>
            <p className="text-white/20 text-[10px] mt-1">Version 2.1.0 · Secure Platform</p>
          </div>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-6 bg-[#f7f8fa]">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="flex items-center gap-2.5 mb-8 lg:hidden">
            <div className="w-9 h-9 bg-[#156235] rounded-xl flex items-center justify-center">
              <Sprout size={18} className="text-white" />
            </div>
            <p className="text-[#0d1117] font-bold text-xl">ReliefTrace</p>
          </div>

          {!selected ? (
            <>
              <div className="mb-6">
                <h1 className="text-2xl font-bold text-[#0d1117]">Sign in to continue</h1>
                <p className="text-slate-500 text-sm mt-1">Select your portal to proceed</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {PORTAL_OPTIONS.map(portal => (
                  <button
                    key={portal.id}
                    onClick={() => setSelected(portal.id)}
                    className={`relative text-left p-4 rounded-xl border-2 bg-white transition-all duration-150 group ${portal.border}`}
                  >
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-3 ${portal.bg} ${portal.text}`}>{portal.icon}</div>
                    <p className={`text-sm font-semibold text-[#1a2130] leading-tight`}>{portal.label}</p>
                    <p className="text-[11px] text-slate-400 mt-1 leading-snug">{portal.description}</p>
                    <ArrowRight size={14} className={`absolute top-4 right-4 ${portal.text} opacity-0 group-hover:opacity-100 transition-opacity`} />
                  </button>
                ))}
              </div>

              <p className="text-center text-xs text-slate-400 mt-6">
                Authorised personnel only. All access is logged and audited.
              </p>
            </>
          ) : (
            <>
              <button onClick={() => setSelected(null)} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 mb-6 transition-colors">
                <ArrowRight size={12} className="rotate-180" /> Back to portal selection
              </button>

              <div className={`flex items-center gap-3 p-3.5 rounded-xl border ${selectedPortal?.border} ${selectedPortal?.bg} mb-6`}>
                <span className={selectedPortal?.text}>{selectedPortal?.icon}</span>
                <div>
                  <p className={`text-sm font-semibold ${selectedPortal?.text}`}>{selectedPortal?.label}</p>
                  <p className="text-xs text-slate-500">{selectedPortal?.demo.sub}</p>
                </div>
              </div>

              <h2 className="text-xl font-bold text-[#0d1117] mb-5">Sign in</h2>

              <div className="space-y-4">
                <Input
                  label="Employee / Farmer ID"
                  placeholder={selectedPortal?.demo.sub ?? 'Enter your ID'}
                  defaultValue={selectedPortal?.id === 'farmer' ? 'TN-MDU-23841' : selectedPortal?.demo.label}
                />
                <div className="relative">
                  <Input
                    label="Password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Enter your password"
                    defaultValue="••••••••"
                    iconRight={
                      <button type="button" onClick={() => setShowPassword(s => !s)} className="text-slate-400 hover:text-slate-600">
                        {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    }
                  />
                </div>
              </div>

              {error && <Alert type="error" className="mt-3">{error}</Alert>}

              <Alert type="info" className="mt-4">
                <strong>Demo mode:</strong> Click Sign In to access the {selectedPortal?.label} as <strong>{selectedPortal?.demo.label}</strong>
              </Alert>

              <Button onClick={handleLogin} loading={loading} className="w-full mt-4" size="lg" iconRight={<ArrowRight size={16} />}>
                Sign In
              </Button>

              <p className="text-center text-xs text-slate-400 mt-4">
                Forgot your credentials? Contact your district administrator.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
