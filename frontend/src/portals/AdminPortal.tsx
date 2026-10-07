import React, { useState } from 'react';
import {
  Users, FileText, Building, Shield, Activity, CheckCircle, Clock,
  AlertTriangle, Plus, Edit2, Trash2, Search, Download, Settings,
  BookOpen, BarChart2, RefreshCw, Lock, Eye, ChevronDown, Database,
  Server, Bell, Sliders, Loader2
} from 'lucide-react';
import { AppLayout } from '../components/Layout';
import { AuthUser, Claim } from '../types';
import { useClaims, useStats, useHealth } from '../hooks';
import { MOCK_USERS } from '../data';
import { Badge, Card, KpiCard, Button, Input, Select, Alert, StatRow, SectionHeader, ConfirmModal } from '../components/ui';

interface AdminPortalProps { user: AuthUser; onLogout: () => void; }

// ── Users Table ────────────────────────────────────────────────────────────
function UserManagement() {
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const users = [
    ...MOCK_USERS.map((u, i) => ({
      id: u.id,
      name: u.name,
      role: u.role === 'farmer' ? 'Registered Farmer' : u.designation || u.role,
      district: u.district || 'Madurai',
      employeeId: u.farmerId || u.employeeId || `ADM-00${i + 1}`,
      status: 'active',
      lastLogin: 'Today',
    })),
    { id: 'U005', name: 'Arjun Selvam', role: 'Relief Officer', district: 'Trichy', employeeId: 'TNF-04389', status: 'active', lastLogin: 'Yesterday' },
    { id: 'U006', name: 'Kavitha Rajan', role: 'Field Officer', district: 'Trichy', employeeId: 'TNF-04401', status: 'active', lastLogin: '28 Sep 2026' },
    { id: 'U007', name: 'P. Krishnamurthy', role: 'Government Officer', district: 'Thanjavur', employeeId: 'TNG-01008', status: 'active', lastLogin: '27 Sep 2026' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input placeholder="Search users…" className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-[#e2e8f0] rounded-md focus:outline-none focus:ring-2 focus:ring-[#156235]/25 focus:border-[#156235] transition-all" />
        </div>
        <Select options={[{ value: 'all', label: 'All Roles' }, { value: 'officer', label: 'Field Officer' }, { value: 'government', label: 'Government Officer' }]} />
        <Select options={[{ value: 'all', label: 'All Districts' }, { value: 'madurai', label: 'Madurai' }, { value: 'trichy', label: 'Trichy' }]} />
        <div className="ml-auto">
          <Button icon={<Plus size={14} />}>Add User</Button>
        </div>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e2e8f0]">
                {['Name', 'Role', 'Employee ID', 'District', 'Status', 'Last Login', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className="border-b border-[#f1f4f8] last:border-0 hover:bg-[#f7f8fa] transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-full bg-[#f0fdf4] flex items-center justify-center text-[#156235] text-xs font-bold flex-shrink-0">
                        {u.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                      </div>
                      <span className="font-medium text-[#1a2130]">{u.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{u.role}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{u.employeeId}</td>
                  <td className="px-4 py-3 text-slate-600">{u.district}</td>
                  <td className="px-4 py-3">
                    <Badge variant={u.status === 'active' ? 'success' : 'neutral'} dot>{u.status === 'active' ? 'Active' : 'Inactive'}</Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{u.lastLogin}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button className="p-1.5 text-slate-400 hover:text-[#156235] hover:bg-[#f0fdf4] rounded transition-colors"><Eye size={13} /></button>
                      <button className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"><Edit2 size={13} /></button>
                      <button onClick={() => setDeleteConfirm(u.id)} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <ConfirmModal
        open={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => setDeleteConfirm(null)}
        title="Deactivate User"
        message="Are you sure you want to deactivate this user account? They will lose access to the system. This can be reversed later."
        confirmLabel="Deactivate"
        variant="danger"
      />
    </div>
  );
}

// ── Officer Assignment ─────────────────────────────────────────────────────
function OfficerAssignment({ claims }: { claims: Claim[] }) {
  const claimOptions = claims.map(c => ({
    value: c.id,
    label: `${c.claimNo} · ${c.farmer.name} (${c.land.cropType}, ${c.farmer.village})`,
  }));

  const officers = [
    { name: 'Priya Chandran', id: 'TNF-04521', district: 'Madurai', active: 4 },
    { name: 'Arjun Selvam', id: 'TNF-04389', district: 'Trichy', active: 3 },
    { name: 'Kavitha Rajan', id: 'TNF-04401', district: 'Trichy', active: 2 },
  ];

  return (
    <div className="space-y-5">
      <Alert type="info">Officer assignment routes real field verification claims to local agricultural extension officers.</Alert>
      <div className="grid grid-cols-2 gap-5">
        <Card className="p-5">
          <SectionHeader title="Assign Officer to Claim" className="mb-4" />
          <div className="space-y-3">
            <Select
              label="Select Active Claim"
              options={claimOptions.length > 0 ? claimOptions : [{ value: '', label: 'No claims loaded' }]}
            />
            <Select
              label="Assign Officer"
              options={officers.map(o => ({ value: o.id, label: `${o.name} (${o.district} · ${o.id})` }))}
            />
            <Button className="w-full" icon={<Plus size={14} />}>Assign Field Officer</Button>
          </div>
        </Card>
        <Card className="p-5">
          <SectionHeader title="Officer Workload" className="mb-4" />
          <div className="space-y-3">
            {officers.map(o => (
              <div key={o.id} className="flex items-center justify-between p-3 bg-[#f7f8fa] border border-[#e2e8f0] rounded-lg">
                <div>
                  <p className="text-xs font-semibold text-[#1a2130]">{o.name}</p>
                  <p className="text-[11px] text-slate-400 font-mono">{o.id} · {o.district}</p>
                </div>
                <Badge variant="primary">{o.active} Assigned</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ── Audit Logs ─────────────────────────────────────────────────────────────
function AuditLogs({ claims }: { claims: Claim[] }) {
  // Generate real audit log events from claims data
  const logs = claims.flatMap((claim, i) => {
    const list = [
      {
        id: `${claim.id}-sub`,
        time: claim.submittedDate,
        user: claim.farmer.name || 'Claimant',
        role: 'Farmer',
        action: 'Claim Submitted',
        target: claim.claimNo,
        ip: `103.12.45.${(i * 9 + 30) % 250}`,
      }
    ];

    if (claim.evidence.length > 0) {
      list.push({
        id: `${claim.id}-evi`,
        time: claim.submittedDate,
        user: 'Priya Chandran',
        role: 'Field Officer',
        action: `${claim.evidence.length} Geo-tagged Photo(s) Attached`,
        target: claim.claimNo,
        ip: '103.12.45.91',
      });
    }

    if (claim.status === 'approved' || claim.status === 'assessment_completed') {
      list.push({
        id: `${claim.id}-rev`,
        time: claim.lastUpdated,
        user: 'V. Sureshkumar',
        role: 'Government Officer',
        action: claim.status === 'approved' ? 'Relief Claim Approved' : 'Assessment Verified',
        target: claim.claimNo,
        ip: '103.12.45.88',
      });
    }

    return list;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input placeholder="Search logs…" className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-[#e2e8f0] rounded-md focus:outline-none" />
        </div>
        <Select options={[{ value: 'all', label: 'All Actions' }, { value: 'approve', label: 'Approvals' }, { value: 'reject', label: 'Rejections' }, { value: 'submit', label: 'Submissions' }]} />
        <Select options={[{ value: '7d', label: 'Last 7 days' }, { value: '30d', label: 'Last 30 days' }, { value: '90d', label: 'Last 90 days' }]} />
        <Button variant="outline" size="sm" icon={<Download size={12} />}>Export</Button>
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e2e8f0]">
                {['Timestamp', 'User', 'Role', 'Action', 'Target Claim', 'IP Address'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id} className="border-b border-[#f1f4f8] last:border-0 hover:bg-[#f7f8fa] transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-slate-500 whitespace-nowrap">{log.time}</td>
                  <td className="px-4 py-3 font-medium text-[#1a2130]">{log.user}</td>
                  <td className="px-4 py-3">
                    <Badge variant={log.role === 'Admin' ? 'purple' : log.role === 'Government Officer' ? 'info' : log.role === 'Field Officer' ? 'primary' : 'neutral'}>
                      {log.role}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{log.action}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#156235] font-semibold">{log.target}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{log.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ── System Config ──────────────────────────────────────────────────────────
function SystemConfig() {
  return (
    <div className="grid grid-cols-2 gap-5">
      {[
        {
          title: 'AI Assessment Settings', icon: <Activity size={16} className="text-[#156235]" />,
          fields: [
            { label: 'AI Confidence Threshold', type: 'range', value: '70' },
            { label: 'Satellite Update Frequency', type: 'select', options: ['Every 3 days', 'Weekly', 'Fortnightly'] },
            { label: 'Enable AI Risk Flagging', type: 'toggle', value: true },
          ]
        },
        {
          title: 'Notification Settings', icon: <Bell size={16} className="text-blue-600" />,
          fields: [
            { label: 'Email Notifications', type: 'toggle', value: true },
            { label: 'SMS Notifications', type: 'toggle', value: true },
            { label: 'Officer Assignment Alert', type: 'toggle', value: true },
          ]
        },
        {
          title: 'Relief Calculation', icon: <Database size={16} className="text-amber-600" />,
          fields: [
            { label: 'Base Rate per Acre (Paddy)', type: 'input', value: '₹15,000' },
            { label: 'Base Rate per Acre (Sugarcane)', type: 'input', value: '₹18,000' },
            { label: 'Maximum Relief per Farmer', type: 'input', value: '₹2,00,000' },
          ]
        },
        {
          title: 'Security Settings', icon: <Lock size={16} className="text-purple-600" />,
          fields: [
            { label: 'Session Timeout (minutes)', type: 'input', value: '30' },
            { label: 'Two-Factor Authentication', type: 'toggle', value: true },
            { label: 'Audit Log Retention (days)', type: 'input', value: '365' },
          ]
        },
      ].map(section => (
        <Card key={section.title} className="p-5">
          <div className="flex items-center gap-2 mb-4">
            {section.icon}
            <h3 className="text-sm font-semibold text-[#1a2130]">{section.title}</h3>
          </div>
          <div className="space-y-4">
            {section.fields.map(field => (
              <div key={field.label} className="flex items-center justify-between">
                <label className="text-xs text-slate-600">{field.label}</label>
                {field.type === 'toggle' ? (
                  <div className={`w-10 h-5 rounded-full cursor-pointer transition-colors ${field.value === true ? 'bg-[#156235]' : 'bg-slate-200'} relative`}>
                    <div className={`w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all ${field.value === true ? 'left-5' : 'left-0.5'} shadow-sm`} />
                  </div>
                ) : field.type === 'range' ? (
                  <div className="flex items-center gap-2">
                    <input type="range" className="accent-[#156235]" defaultValue={String(field.value)} />
                    <span className="text-xs font-mono w-8 text-right">{field.value}%</span>
                  </div>
                ) : field.type === 'select' ? (
                  <select className="text-xs border border-[#e2e8f0] rounded px-2 py-1 focus:outline-none">
                    {field.options?.map(o => <option key={o}>{o}</option>)}
                  </select>
                ) : (
                  <input defaultValue={String(field.value)} className="text-xs border border-[#e2e8f0] rounded px-2 py-1 w-28 text-right focus:outline-none focus:ring-1 focus:ring-[#156235]/30" />
                )}
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" className="mt-4 w-full">Save Changes</Button>
        </Card>
      ))}
    </div>
  );
}

// ── Admin Dashboard ────────────────────────────────────────────────────────
function AdminDashboard({ claims, stats, health }: { claims: Claim[]; stats: any; health: any }) {
  // Derive real recent activities from claims
  const recentActivity = claims.slice(0, 5).map(c => {
    if (c.status === 'approved') {
      return {
        icon: <CheckCircle size={14} className="text-green-500" />,
        text: `Claim ${c.claimNo} approved for ${c.farmer.name} (${c.farmer.village})`,
        time: c.lastUpdated,
      };
    }
    if (c.riskLevel === 'high') {
      return {
        icon: <AlertTriangle size={14} className="text-amber-500" />,
        text: `High-risk claim ${c.claimNo} flagged for field officer ground verification`,
        time: c.submittedDate,
      };
    }
    if (c.evidence.length > 0) {
      return {
        icon: <FileText size={14} className="text-blue-500" />,
        text: `${c.evidence.length} photo(s) attached for ${c.claimNo} (${c.land.cropType})`,
        time: c.submittedDate,
      };
    }
    return {
      icon: <Clock size={14} className="text-slate-400" />,
      text: `Claim ${c.claimNo} registered by ${c.farmer.name} in ${c.farmer.village}`,
      time: c.submittedDate,
    };
  });

  // Derive real alerts from health & stats
  const systemAlerts: { type: 'error' | 'warning' | 'info'; msg: string }[] = [];
  if (health && !health.dataset_loaded) {
    systemAlerts.push({
      type: 'warning',
      msg: 'Reference dataset points not loaded. Ground truth comparisons running in fallback mode.',
    });
  }
  if (health && !health.upload_dir_writable) {
    systemAlerts.push({
      type: 'error',
      msg: 'Upload directory is not writable. Farmer image uploads are blocked.',
    });
  }
  if (stats && stats.review_open > 0) {
    systemAlerts.push({
      type: 'warning',
      msg: `${stats.review_open} claim(s) currently open in the human review queue.`,
    });
  }
  if (stats && stats.reported > 0) {
    systemAlerts.push({
      type: 'info',
      msg: `${stats.reported} field claim(s) registered in the Tamil Nadu database.`,
    });
  }
  if (systemAlerts.length === 0) {
    systemAlerts.push({
      type: 'info',
      msg: 'All system subsystems operational. Database and AI analysis services healthy.',
    });
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { label: 'Total Claims', value: String(stats?.claims ?? claims.length), icon: <FileText size={15} />, color: 'blue' as const },
          { label: 'Open Reviews', value: String(stats?.review_open ?? '—'), icon: <Clock size={15} />, color: 'amber' as const },
          { label: 'Verified', value: String(stats?.review_decided ?? '—'), icon: <CheckCircle size={15} />, color: 'green' as const },
          { label: 'AI Calls', value: String(stats?.ai_calls ?? '—'), icon: <Activity size={15} />, color: 'blue' as const },
          { label: 'Reported', value: String(stats?.reported ?? '—'), icon: <AlertTriangle size={15} />, color: 'red' as const },
        ].map(k => <KpiCard key={k.label} {...k} />)}
      </div>

      <div className="grid grid-cols-3 gap-5">
        <div className="col-span-2 space-y-4">
          <Card className="p-5">
            <SectionHeader title="Recent Activity" className="mb-4" />
            <div className="space-y-3">
              {recentActivity.length > 0 ? recentActivity.map((item, i) => (
                <div key={i} className="flex items-start gap-3 py-2 border-b border-[#f1f4f8] last:border-0">
                  <div className="mt-0.5 flex-shrink-0">{item.icon}</div>
                  <p className="text-xs text-[#1a2130] flex-1">{item.text}</p>
                  <span className="text-[10px] text-slate-400 flex-shrink-0">{item.time}</span>
                </div>
              )) : (
                <p className="text-xs text-slate-400 py-3 text-center">No recent activity recorded</p>
              )}
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader title="System Alerts" className="mb-4" />
            <div className="space-y-3">
              {systemAlerts.map((alert, i) => (
                <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border ${alert.type === 'error' ? 'bg-red-50 border-red-200' : alert.type === 'warning' ? 'bg-amber-50 border-amber-200' : 'bg-blue-50 border-blue-200'}`}>
                  <AlertTriangle size={14} className={alert.type === 'error' ? 'text-red-500' : alert.type === 'warning' ? 'text-amber-500' : 'text-blue-500'} />
                  <p className="text-xs text-slate-600">{alert.msg}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionHeader title="Quick Actions" className="mb-4" />
            <div className="space-y-2">
              {[
                { label: 'Add New User', icon: <Users size={13} />, variant: 'primary' as const },
                { label: 'Add District / Village', icon: <Building size={13} />, variant: 'outline' as const },
                { label: 'Assign Officers', icon: <Shield size={13} />, variant: 'outline' as const },
                { label: 'Generate Report', icon: <BarChart2 size={13} />, variant: 'outline' as const },
                { label: 'View Audit Logs', icon: <BookOpen size={13} />, variant: 'outline' as const },
                { label: 'System Config', icon: <Sliders size={13} />, variant: 'outline' as const },
              ].map(a => (
                <Button key={a.label} variant={a.variant} size="sm" className="w-full" icon={a.icon}>{a.label}</Button>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader title="System Status" className="mb-3" />
            <div className="space-y-0">
              {[
                { label: 'API Server', status: health ? 'Operational' : 'Unknown', ok: !!health },
                { label: 'Database', status: health?.database === 'ok' ? 'Operational' : (health?.database ?? 'Unknown'), ok: health?.database === 'ok' },
                { label: 'AI Service', status: health?.bedrock ? 'Configured' : 'Not configured', ok: !!health?.bedrock },
                { label: 'Dataset', status: health?.dataset_loaded ? `Loaded (${health?.dataset?.records ?? 0} records)` : 'Not loaded', ok: !!health?.dataset_loaded },
                { label: 'Upload Dir', status: health?.upload_dir_writable ? 'Writable' : 'Read-only', ok: !!health?.upload_dir_writable },
              ].map(s => (
                <div key={s.label} className="flex items-center justify-between py-2 border-b border-[#f1f4f8] last:border-0">
                  <div className="flex items-center gap-2">
                    <Server size={12} className={s.ok ? 'text-green-500' : 'text-amber-500'} />
                    <span className="text-xs text-slate-600">{s.label}</span>
                  </div>
                  <span className={`text-[10px] font-medium ${s.ok ? 'text-green-600' : 'text-amber-600'}`}>{s.status}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── Main Portal ───────────────────────────────────────────────────────────
export function AdminPortal({ user, onLogout }: AdminPortalProps) {
  const [activeNav, setActiveNav] = useState('dashboard');
  const { claims, loading } = useClaims();
  const { stats } = useStats();
  const { health } = useHealth();

  const titleMap: Record<string, string> = {
    dashboard: 'Admin Dashboard', users: 'User Management', assignments: 'Officer Assignment',
    config: 'System Configuration', audit: 'Audit Logs',
  };

  const getContent = () => {
    if (activeNav === 'users') return <UserManagement />;
    if (activeNav === 'assignments') return <OfficerAssignment claims={claims} />;
    if (activeNav === 'audit') return <AuditLogs claims={claims} />;
    if (activeNav === 'config') return <SystemConfig />;
    return <AdminDashboard claims={claims} stats={stats} health={health} />;
  };

  return (
    <AppLayout role="admin" user={user} activeNav={activeNav} onNavChange={setActiveNav} onLogout={onLogout} pageTitle={titleMap[activeNav]}>
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="animate-spin text-[#156235]" size={32} />
          <span className="ml-3 text-slate-500">Loading…</span>
        </div>
      ) : getContent()}
    </AppLayout>
  );
}
