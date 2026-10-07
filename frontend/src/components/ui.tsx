import React, { useState, useRef, useEffect } from 'react';
import { X, ChevronDown, Check, AlertTriangle, Info, CheckCircle, XCircle } from 'lucide-react';

// ── Button ─────────────────────────────────────────────────────────────────
type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'success';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-[#156235] text-white hover:bg-[#0f4d28] focus:ring-[#156235]/30',
  secondary: 'bg-[#1e40af] text-white hover:bg-[#1e3a8a] focus:ring-[#1e40af]/30',
  outline: 'bg-white text-[#1a2130] border border-[#e2e8f0] hover:bg-[#f7f8fa] focus:ring-[#156235]/20',
  ghost: 'bg-transparent text-[#64748b] hover:bg-[#f1f4f8] hover:text-[#1a2130] focus:ring-transparent',
  danger: 'bg-[#dc2626] text-white hover:bg-[#b91c1c] focus:ring-[#dc2626]/30',
  success: 'bg-[#16a34a] text-white hover:bg-[#15803d] focus:ring-[#16a34a]/30',
};
const sizeClasses: Record<ButtonSize, string> = {
  sm: 'text-xs px-3 py-1.5 gap-1.5',
  md: 'text-sm px-4 py-2 gap-2',
  lg: 'text-base px-5 py-2.5 gap-2',
};

export function Button({ variant = 'primary', size = 'md', loading, icon, iconRight, children, className = '', disabled, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center font-medium rounded-[6px] transition-all duration-150 focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {loading ? <Spinner size={size === 'sm' ? 14 : 16} /> : icon}
      {children}
      {iconRight}
    </button>
  );
}

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg className="animate-spin" width={size} height={size} viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.3" strokeWidth="2" />
      <path d="M14 8a6 6 0 00-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

// ── Badge ──────────────────────────────────────────────────────────────────
type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'primary' | 'purple';
interface BadgeProps { variant?: BadgeVariant; children: React.ReactNode; className?: string; dot?: boolean; }

const badgeVariants: Record<BadgeVariant, string> = {
  success: 'bg-green-50 text-green-700 border-green-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  error: 'bg-red-50 text-red-700 border-red-200',
  info: 'bg-blue-50 text-blue-700 border-blue-200',
  neutral: 'bg-slate-50 text-slate-600 border-slate-200',
  primary: 'bg-[#f0fdf4] text-[#156235] border-[#bbf7d0]',
  purple: 'bg-purple-50 text-purple-700 border-purple-200',
};

export function Badge({ variant = 'neutral', children, className = '', dot }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded border ${badgeVariants[variant]} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${variant === 'success' ? 'bg-green-500' : variant === 'warning' ? 'bg-amber-500' : variant === 'error' ? 'bg-red-500' : variant === 'info' ? 'bg-blue-500' : variant === 'primary' ? 'bg-[#156235]' : 'bg-slate-400'}`} />}
      {children}
    </span>
  );
}

// ── Card ───────────────────────────────────────────────────────────────────
interface CardProps { children: React.ReactNode; className?: string; onClick?: () => void; hoverable?: boolean; }
export function Card({ children, className = '', onClick, hoverable }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`bg-white border border-[#e2e8f0] rounded-lg shadow-sm ${hoverable ? 'hover:shadow-md hover:border-[#cbd5e1] transition-all duration-150 cursor-pointer' : ''} ${className}`}
    >{children}</div>
  );
}

// ── KPI Card ───────────────────────────────────────────────────────────────
interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  trend?: { value: string; up: boolean };
  icon: React.ReactNode;
  color?: 'green' | 'blue' | 'amber' | 'red' | 'purple';
  onClick?: () => void;
}
const kpiColors = {
  green: { bg: 'bg-green-50', text: 'text-green-700', icon: 'bg-green-100 text-green-600' },
  blue: { bg: 'bg-blue-50', text: 'text-blue-700', icon: 'bg-blue-100 text-blue-600' },
  amber: { bg: 'bg-amber-50', text: 'text-amber-700', icon: 'bg-amber-100 text-amber-600' },
  red: { bg: 'bg-red-50', text: 'text-red-700', icon: 'bg-red-100 text-red-600' },
  purple: { bg: 'bg-purple-50', text: 'text-purple-700', icon: 'bg-purple-100 text-purple-600' },
};

export function KpiCard({ label, value, sub, trend, icon, color = 'blue', onClick }: KpiCardProps) {
  const c = kpiColors[color];
  return (
    <Card hoverable={!!onClick} onClick={onClick} className="p-5">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
          <p className={`text-3xl font-bold mt-1 ${c.text}`}>{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
          {trend && (
            <p className={`text-xs mt-1 font-medium ${trend.up ? 'text-green-600' : 'text-red-500'}`}>
              {trend.up ? '↑' : '↓'} {trend.value}
            </p>
          )}
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${c.icon}`}>
          {icon}
        </div>
      </div>
    </Card>
  );
}

// ── Input ─────────────────────────────────────────────────────────────────
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
}
export function Input({ label, error, icon, iconRight, className = '', id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="flex flex-col gap-1">
      {label && <label htmlFor={inputId} className="text-xs font-medium text-slate-600">{label}</label>}
      <div className="relative">
        {icon && <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">{icon}</span>}
        <input
          id={inputId}
          className={`w-full bg-white border ${error ? 'border-red-400' : 'border-[#e2e8f0]'} rounded-[6px] text-sm text-[#1a2130] placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#156235]/25 focus:border-[#156235] transition-all ${icon ? 'pl-9' : 'pl-3'} ${iconRight ? 'pr-9' : 'pr-3'} py-2 ${className}`}
          {...props}
        />
        {iconRight && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">{iconRight}</span>}
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

// ── Select ─────────────────────────────────────────────────────────────────
interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
}
export function Select({ label, options, className = '', id, ...props }: SelectProps) {
  const selectId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="flex flex-col gap-1">
      {label && <label htmlFor={selectId} className="text-xs font-medium text-slate-600">{label}</label>}
      <div className="relative">
        <select
          id={selectId}
          className={`w-full appearance-none bg-white border border-[#e2e8f0] rounded-[6px] text-sm text-[#1a2130] pl-3 pr-8 py-2 focus:outline-none focus:ring-2 focus:ring-[#156235]/25 focus:border-[#156235] transition-all ${className}`}
          {...props}
        >
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      </div>
    </div>
  );
}

// ── Textarea ──────────────────────────────────────────────────────────────
interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
}
export function Textarea({ label, className = '', id, ...props }: TextareaProps) {
  const taId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="flex flex-col gap-1">
      {label && <label htmlFor={taId} className="text-xs font-medium text-slate-600">{label}</label>}
      <textarea
        id={taId}
        className={`w-full bg-white border border-[#e2e8f0] rounded-[6px] text-sm text-[#1a2130] placeholder:text-slate-400 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#156235]/25 focus:border-[#156235] transition-all resize-none ${className}`}
        {...props}
      />
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────
interface TabsProps {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}
export function Tabs({ tabs, active, onChange, className = '' }: TabsProps) {
  return (
    <div className={`flex border-b border-[#e2e8f0] ${className}`}>
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-all duration-150 ${active === tab.id ? 'border-[#156235] text-[#156235]' : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'}`}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${active === tab.id ? 'bg-[#156235] text-white' : 'bg-slate-100 text-slate-500'}`}>{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────
interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
}
export function Modal({ open, onClose, title, children, footer, size = 'md' }: ModalProps) {
  if (!open) return null;
  const sizeMap = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className={`relative bg-white rounded-xl shadow-xl border border-[#e2e8f0] w-full mx-4 ${sizeMap[size]} max-h-[90vh] flex flex-col`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#e2e8f0]">
          <h3 className="text-base font-semibold text-[#1a2130]">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-4">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-[#e2e8f0] bg-[#f7f8fa] rounded-b-xl flex items-center justify-end gap-3">{footer}</div>}
      </div>
    </div>
  );
}

// ── Alert ─────────────────────────────────────────────────────────────────
type AlertType = 'info' | 'success' | 'warning' | 'error';
interface AlertProps { type?: AlertType; title?: string; children: React.ReactNode; className?: string; }
const alertStyles: Record<AlertType, { bg: string; border: string; icon: React.ReactNode }> = {
  info: { bg: 'bg-blue-50', border: 'border-blue-200', icon: <Info size={15} className="text-blue-500" /> },
  success: { bg: 'bg-green-50', border: 'border-green-200', icon: <CheckCircle size={15} className="text-green-600" /> },
  warning: { bg: 'bg-amber-50', border: 'border-amber-200', icon: <AlertTriangle size={15} className="text-amber-500" /> },
  error: { bg: 'bg-red-50', border: 'border-red-200', icon: <XCircle size={15} className="text-red-500" /> },
};
export function Alert({ type = 'info', title, children, className = '' }: AlertProps) {
  const s = alertStyles[type];
  return (
    <div className={`flex gap-3 p-3.5 rounded-lg border ${s.bg} ${s.border} ${className}`}>
      <div className="mt-0.5 flex-shrink-0">{s.icon}</div>
      <div className="flex-1 min-w-0">
        {title && <p className="text-xs font-semibold text-slate-700 mb-0.5">{title}</p>}
        <p className="text-xs text-slate-600">{children}</p>
      </div>
    </div>
  );
}

// ── Table ─────────────────────────────────────────────────────────────────
interface TableColumn<T> { key: string; header: string; render?: (row: T) => React.ReactNode; className?: string; }
interface TableProps<T extends Record<string, unknown>> { columns: TableColumn<T>[]; data: T[]; onRowClick?: (row: T) => void; emptyMessage?: string; }
export function Table<T extends Record<string, unknown>>({ columns, data, onRowClick, emptyMessage = 'No records found' }: TableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#e2e8f0]">
            {columns.map(col => (
              <th key={col.key} className={`px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap ${col.className ?? ''}`}>{col.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr><td colSpan={columns.length} className="px-4 py-12 text-center text-slate-400">{emptyMessage}</td></tr>
          ) : data.map((row, i) => (
            <tr key={i} onClick={() => onRowClick?.(row)} className={`border-b border-[#f1f4f8] last:border-0 ${onRowClick ? 'hover:bg-[#f7f8fa] cursor-pointer' : ''} transition-colors`}>
              {columns.map(col => (
                <td key={col.key} className={`px-4 py-3 text-slate-700 ${col.className ?? ''}`}>
                  {col.render ? col.render(row) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Progress Bar ───────────────────────────────────────────────────────────
interface ProgressBarProps { value: number; max?: number; color?: string; label?: string; showValue?: boolean; height?: number; className?: string; }
export function ProgressBar({ value, max = 100, color, label, showValue, height = 8, className = '' }: ProgressBarProps) {
  const pct = Math.min(100, (value / max) * 100);
  const barColor = color || (pct >= 76 ? '#dc2626' : pct >= 51 ? '#f97316' : pct >= 26 ? '#eab308' : '#16a34a');
  return (
    <div className="flex flex-col gap-1">
      {(label || showValue) && (
        <div className="flex items-center justify-between">
          {label && <span className="text-xs text-slate-600">{label}</span>}
          {showValue && <span className="text-xs font-semibold text-slate-700">{value}%</span>}
        </div>
      )}
      <div className={`w-full bg-slate-100 rounded-full overflow-hidden ${className}`} style={{ height }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: barColor }} />
      </div>
    </div>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────
interface TimelineItem { date: string; event: string; actor: string; notes?: string; }
export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <div className="flex flex-col gap-0">
      {items.map((item, i) => (
        <div key={i} className="flex gap-4">
          <div className="flex flex-col items-center">
            <div className="w-3 h-3 rounded-full bg-[#156235] border-2 border-[#bbf7d0] flex-shrink-0 mt-1" />
            {i < items.length - 1 && <div className="w-0.5 bg-[#e2e8f0] flex-1 my-1" />}
          </div>
          <div className="pb-5 flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-[#1a2130]">{item.event}</span>
              <span className="font-mono text-xs text-slate-400">{item.date}</span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">by {item.actor}</p>
            {item.notes && <p className="text-xs text-slate-600 mt-1 bg-[#f7f8fa] border border-[#e2e8f0] rounded p-2">{item.notes}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Risk Indicator Row ─────────────────────────────────────────────────────
type RiskStatus = 'verified' | 'review_required' | 'no_issue' | 'flagged';
interface RiskRowProps { indicator: string; status: RiskStatus; details: string; }
const riskStatusConfig: Record<RiskStatus, { label: string; icon: React.ReactNode; bg: string; text: string }> = {
  verified: { label: 'Verified', icon: <Check size={12} />, bg: 'bg-green-50 border-green-200', text: 'text-green-700' },
  no_issue: { label: 'No Issue', icon: <Check size={12} />, bg: 'bg-slate-50 border-slate-200', text: 'text-slate-600' },
  review_required: { label: 'Review Required', icon: <AlertTriangle size={12} />, bg: 'bg-amber-50 border-amber-200', text: 'text-amber-700' },
  flagged: { label: 'Flagged', icon: <XCircle size={12} />, bg: 'bg-red-50 border-red-200', text: 'text-red-700' },
};
export function RiskRow({ indicator, status, details }: RiskRowProps) {
  const cfg = riskStatusConfig[status];
  return (
    <div className="flex items-start gap-4 py-3 border-b border-[#f1f4f8] last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[#1a2130]">{indicator}</p>
        <p className="text-xs text-slate-500 mt-0.5">{details}</p>
      </div>
      <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded border ${cfg.bg} ${cfg.text} whitespace-nowrap flex-shrink-0`}>
        {cfg.icon}{cfg.label}
      </span>
    </div>
  );
}

// ── Section Header ─────────────────────────────────────────────────────────
interface SectionHeaderProps { title: string; subtitle?: string; action?: React.ReactNode; className?: string; }
export function SectionHeader({ title, subtitle, action, className = '' }: SectionHeaderProps) {
  return (
    <div className={`flex items-start justify-between gap-4 ${className}`}>
      <div>
        <h2 className="text-base font-semibold text-[#1a2130]">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

// ── Stat Row ──────────────────────────────────────────────────────────────
export function StatRow({ label, value, mono }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-[#f1f4f8] last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-sm font-medium text-[#1a2130] ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

// ── Confirm Modal ─────────────────────────────────────────────────────────
interface ConfirmModalProps { open: boolean; onClose: () => void; onConfirm: () => void; title: string; message: string; confirmLabel?: string; variant?: 'danger' | 'success' | 'warning'; }
export function ConfirmModal({ open, onClose, onConfirm, title, message, confirmLabel = 'Confirm', variant = 'danger' }: ConfirmModalProps) {
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm"
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button variant={variant === 'success' ? 'success' : variant === 'warning' ? 'primary' : 'danger'} onClick={onConfirm}>{confirmLabel}</Button></>}
    >
      <p className="text-sm text-slate-600">{message}</p>
    </Modal>
  );
}

// ── Empty State ───────────────────────────────────────────────────────────
export function EmptyState({ icon, title, description, action }: { icon: React.ReactNode; title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-4">{icon}</div>
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {description && <p className="text-xs text-slate-400 mt-1 max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ── Dropdown Menu ─────────────────────────────────────────────────────────
interface DropdownItem { label: string; icon?: React.ReactNode; onClick: () => void; danger?: boolean; divider?: boolean; }
interface DropdownMenuProps { trigger: React.ReactNode; items: DropdownItem[]; align?: 'left' | 'right'; }
export function DropdownMenu({ trigger, items, align = 'right' }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handle = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);
  return (
    <div ref={ref} className="relative">
      <div onClick={() => setOpen(o => !o)}>{trigger}</div>
      {open && (
        <div className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} top-full mt-1 bg-white border border-[#e2e8f0] rounded-lg shadow-lg z-30 py-1 min-w-[160px]`}>
          {items.map((item, i) => (
            item.divider ? <div key={i} className="h-px bg-[#e2e8f0] my-1" /> :
            <button key={i} onClick={() => { item.onClick(); setOpen(false); }}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors ${item.danger ? 'text-red-600 hover:bg-red-50' : 'text-slate-700 hover:bg-[#f7f8fa]'}`}
            >{item.icon}{item.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Utility ────────────────────────────────────────────────────────────────
export function claimStatusLabel(s: string): string {
  const labels: Record<string, string> = {
    submitted: 'Submitted', assigned: 'Assigned', field_verification: 'Field Verification',
    assessment_completed: 'Assessment Completed', government_review: 'Govt. Review',
    approved: 'Approved', rejected: 'Rejected', additional_evidence: 'Evidence Requested',
  };
  return labels[s] ?? s;
}

export function claimStatusVariant(s: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    submitted: 'info', assigned: 'neutral', field_verification: 'info',
    assessment_completed: 'primary', government_review: 'purple', approved: 'success',
    rejected: 'error', additional_evidence: 'warning',
  };
  return map[s] ?? 'neutral';
}

export function riskBadgeVariant(r: string): BadgeVariant {
  return r === 'high' ? 'error' : r === 'medium' ? 'warning' : 'success';
}
