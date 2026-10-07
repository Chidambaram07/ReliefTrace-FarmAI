import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area,
  LineChart, Line
} from 'recharts';
import type { DistrictStats } from '../types';

const COLORS = { primary: '#156235', blue: '#1e40af', amber: '#d97706', red: '#dc2626', teal: '#0d9488', purple: '#7c3aed' };

const tooltipStyle = {
  backgroundColor: '#0d1117',
  border: '1px solid #2d3748',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: 12,
  padding: '8px 12px',
};

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { color: string; name: string; value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={tooltipStyle}>
      {label && <p className="font-semibold text-white text-xs mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="text-xs" style={{ color: p.color }}>{p.name}: <span className="font-semibold">{p.value}</span></p>
      ))}
    </div>
  );
}

function EmptyState({ height = 200 }: { height?: number }) {
  return <div className="flex items-center justify-center text-sm text-slate-400" style={{ height }}>No data available</div>;
}

// ── Risk / Damage Distribution ───────────────────────────────────────────────
export function DamageDistributionChart({ data }: { data: { range: string; count: number; color: string }[] }) {
  const chartData = data.map(d => ({ name: d.range, Claims: d.count, fill: d.color }));
  if (chartData.length === 0 || chartData.every(d => d.Claims === 0)) return <EmptyState />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chartData} barSize={32} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f4f8" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="Claims" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, index) => <Cell key={index} fill={entry.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Claims Over Time ───────────────────────────────────────────────────────
export function ClaimsOverTimeChart({ data }: { data: { month: string; claims: number }[] }) {
  if (data.length === 0) return <EmptyState />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
        <defs>
          <linearGradient id="claimsGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.2} />
            <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f4f8" vertical={false} />
        <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <Area type="monotone" dataKey="claims" name="Claims" stroke={COLORS.primary} strokeWidth={2} fill="url(#claimsGrad)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Claim Status Donut ─────────────────────────────────────────────────────
export function ClaimStatusDonut({ data }: { data: { name: string; value: number; color: string }[] }) {
  if (data.every(d => d.value === 0)) return <EmptyState height={220} />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value" paddingAngle={2}>
          {data.map((entry, i) => <Cell key={i} fill={entry.color} />)}
        </Pie>
        <Tooltip formatter={(v) => [v, '']} contentStyle={tooltipStyle} />
        <Legend formatter={(value) => <span style={{ color: '#64748b', fontSize: 11 }}>{value}</span>} iconSize={8} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── District Claims Bar ────────────────────────────────────────────────────
export function DistrictClaimsChart({ data }: { data: DistrictStats[] }) {
  if (data.length === 0) return <EmptyState height={220} />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} layout="vertical" barSize={14} margin={{ top: 0, right: 15, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f4f8" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="district" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} width={70} />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="claims" name="Total Claims" fill={COLORS.primary} radius={[0, 3, 3, 0]} />
        <Bar dataKey="approved" name="Approved" fill={COLORS.teal} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Crop Damage Chart ──────────────────────────────────────────────────────
export function CropDamageChart({ data }: { data: { crop: string; claims: number; avgDamage: number }[] }) {
  if (data.length === 0) return <EmptyState height={220} />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} barSize={22} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f4f8" vertical={false} />
        <XAxis dataKey="crop" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="claims" name="Claims" fill={COLORS.blue} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Damage Assessment Comparison ───────────────────────────────────────────
export function DamageComparisonChart({ reported, aiAssisted, officerAssessed }: { reported: number; aiAssisted: number; officerAssessed: number | null }) {
  const data = [
    { name: 'Farmer Reported', value: reported, fill: '#dc2626' },
    { name: 'AI-Assisted Estimate', value: aiAssisted, fill: '#f97316' },
    ...(officerAssessed !== null ? [{ name: 'Officer Assessment', value: officerAssessed, fill: '#156235' }] : []),
  ];
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} barSize={36} margin={{ top: 5, right: 20, left: -15, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f4f8" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <Tooltip formatter={(v) => [`${v}%`, 'Damage']} contentStyle={tooltipStyle} />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Relief Payment Status ──────────────────────────────────────────────────
export function ReliefPaymentChart({ data }: { data: { name: string; value: number; color: string }[] }) {
  if (data.every(d => d.value === 0)) return <EmptyState height={200} />;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={false} labelLine={false}>
          {data.map((entry, i) => <Cell key={i} fill={entry.color} />)}
        </Pie>
        <Tooltip formatter={(v) => [v, 'Claims']} contentStyle={tooltipStyle} />
        <Legend formatter={(value) => <span style={{ color: '#64748b', fontSize: 11 }}>{value}</span>} iconSize={8} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Monthly Trend Line ─────────────────────────────────────────────────────
export function MonthlyTrendChart({ data }: { data: { month: string; claims: number }[] }) {
  if (data.length === 0) return <EmptyState height={160} />;
  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f4f8" vertical={false} />
        <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <Line type="monotone" dataKey="claims" name="Claims" stroke={COLORS.primary} strokeWidth={2.5} dot={{ r: 3, fill: COLORS.primary }} activeDot={{ r: 5 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
