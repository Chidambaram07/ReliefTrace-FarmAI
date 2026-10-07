import React, { useState } from 'react';
import {
  LayoutDashboard, FileText, Map, BarChart2,
  Users, ClipboardList, Sliders, BookOpen, Home, PlusCircle,
  ChevronRight, Search, HelpCircle, LogOut, ChevronDown,
  Menu, Bell, Sprout
} from 'lucide-react';
import { Portal, AuthUser } from '../types';
import { Badge } from './ui';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: string | number;
  badgeVariant?: 'warning' | 'error' | 'info';
}

const OFFICER_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
  { id: 'claims', label: 'Review Queue', icon: <FileText size={16} /> },
  { id: 'map', label: 'GIS Map', icon: <Map size={16} /> },
];

const GOVERNMENT_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
  { id: 'verified-claims', label: 'Verified Claims', icon: <FileText size={16} /> },
  { id: 'analytics', label: 'Analytics', icon: <BarChart2 size={16} /> },
];

const ADMIN_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
  { id: 'users', label: 'User Management', icon: <Users size={16} /> },
  { id: 'assignments', label: 'Officer Assignment', icon: <ClipboardList size={16} /> },
  { id: 'config', label: 'System Config', icon: <Sliders size={16} /> },
  { id: 'audit', label: 'Audit Logs', icon: <BookOpen size={16} /> },
];

const FARMER_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <Home size={16} /> },
  { id: 'submit', label: 'Submit Claim', icon: <PlusCircle size={16} /> },
];

function getNav(role: Portal): NavItem[] {
  if (role === 'officer') return OFFICER_NAV;
  if (role === 'government') return GOVERNMENT_NAV;
  if (role === 'admin') return ADMIN_NAV;
  return FARMER_NAV;
}

function roleMeta(role: Portal) {
  if (role === 'officer') return { label: 'Field / Relief Officer', color: 'text-[#156235]', bg: 'bg-[#f0fdf4]' };
  if (role === 'government') return { label: 'Government Officer', color: 'text-[#1e40af]', bg: 'bg-blue-50' };
  if (role === 'admin') return { label: 'Administrator', color: 'text-purple-700', bg: 'bg-purple-50' };
  return { label: 'Farmer Portal', color: 'text-teal-700', bg: 'bg-teal-50' };
}

interface LayoutProps {
  role: Portal;
  user: AuthUser;
  activeNav: string;
  onNavChange: (id: string) => void;
  onLogout: () => void;
  children: React.ReactNode;
  pageTitle?: string;
  pageActions?: React.ReactNode;
  breadcrumb?: string;
}

export function AppLayout({ role, user, activeNav, onNavChange, onLogout, children, pageTitle, pageActions, breadcrumb }: LayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navItems = getNav(role);
  const meta = roleMeta(role);
  const [searchVal, setSearchVal] = useState('');

  const Sidebar = (
    <aside className="flex flex-col bg-[#0d1117] w-[220px] flex-shrink-0 h-full">
      {/* Logo */}
      <div className="px-5 pt-5 pb-4 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-[#156235] rounded-lg flex items-center justify-center flex-shrink-0">
            <Sprout size={16} className="text-white" />
          </div>
          <div>
            <p className="text-white font-bold text-base leading-none">ReliefTrace</p>
            <p className="text-white/40 text-[10px] mt-0.5 font-mono">v2.1.0</p>
          </div>
        </div>
      </div>

      {/* Role badge */}
      <div className="px-4 py-3 border-b border-white/10">
        <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded ${meta.bg} ${meta.color}`}>{meta.label}</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 scroll-thin">
        <div className="flex flex-col gap-0.5 px-2">
          {navItems.map(item => (
            <button
              key={item.id}
              onClick={() => { onNavChange(item.id); setMobileOpen(false); }}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-150 group ${activeNav === item.id ? 'bg-[#156235] text-white' : 'text-white/60 hover:text-white hover:bg-white/10'}`}
            >
              <span className={`flex-shrink-0 ${activeNav === item.id ? 'text-white' : 'text-white/50 group-hover:text-white/80'}`}>{item.icon}</span>
              <span className="flex-1 text-left">{item.label}</span>
              {item.badge !== undefined && (
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeNav === item.id ? 'bg-white/20 text-white' : item.badgeVariant === 'error' ? 'bg-red-500 text-white' : item.badgeVariant === 'warning' ? 'bg-amber-500 text-white' : 'bg-blue-500 text-white'}`}>{item.badge}</span>
              )}
            </button>
          ))}
        </div>
      </nav>

      {/* User profile */}
      <div className="p-4 border-t border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-[#156235] flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {user.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-xs font-medium truncate">{user.name}</p>
            <p className="text-white/40 text-[10px] truncate">{user.designation ?? user.district ?? ''}</p>
          </div>
          <button onClick={onLogout} className="text-white/40 hover:text-white transition-colors" title="Sign out"><LogOut size={14} /></button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-[#f7f8fa]">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex">{Sidebar}</div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <div className="relative flex w-[220px]">{Sidebar}</div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top header */}
        <header className="flex items-center gap-4 px-5 h-14 bg-white border-b border-[#e2e8f0] flex-shrink-0">
          <button className="lg:hidden text-slate-500" onClick={() => setMobileOpen(true)}><Menu size={20} /></button>

          {/* Search */}
          <div className="relative flex-1 max-w-sm hidden sm:block">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text" placeholder="Search claims, farmers, surveys…" value={searchVal} onChange={e => setSearchVal(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-sm bg-[#f7f8fa] border border-[#e2e8f0] rounded-md focus:outline-none focus:ring-2 focus:ring-[#156235]/25 focus:border-[#156235] transition-all"
            />
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-2">
            <button className="w-8 h-8 flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-[#f7f8fa] rounded-md transition-colors relative">
              <Bell size={16} />
              <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full border border-white" />
            </button>
            <button className="w-8 h-8 flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-[#f7f8fa] rounded-md transition-colors">
              <HelpCircle size={16} />
            </button>
            <div className="h-6 w-px bg-[#e2e8f0]" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-[#156235] flex items-center justify-center text-white text-xs font-bold">
                {user.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
              </div>
              <span className="text-sm font-medium text-[#1a2130] hidden md:block max-w-[120px] truncate">{user.name}</span>
              <ChevronDown size={12} className="text-slate-400 hidden md:block" />
            </div>
          </div>
        </header>

        {/* Page header */}
        {pageTitle && (
          <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-[#e2e8f0] flex-shrink-0">
            <div>
              {breadcrumb && <p className="text-xs text-slate-400 mb-0.5 flex items-center gap-1">{breadcrumb.split(' / ').map((b, i, arr) => <React.Fragment key={i}><span>{b}</span>{i < arr.length - 1 && <ChevronRight size={10} />}</React.Fragment>)}</p>}
              <h1 className="text-lg font-semibold text-[#1a2130]">{pageTitle}</h1>
            </div>
            {pageActions && <div className="flex items-center gap-2">{pageActions}</div>}
          </div>
        )}

        {/* Page content */}
        <main className="flex-1 overflow-y-auto scroll-thin p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
