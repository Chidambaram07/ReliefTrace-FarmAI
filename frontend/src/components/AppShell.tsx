import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, PlusCircle, FlaskConical, Sprout,
} from 'lucide-react';

const NAV = [
  { to: '/', icon: <LayoutDashboard size={16} />, label: 'Dashboard', end: true },
  { to: '/submit', icon: <PlusCircle size={16} />, label: 'Submit Claim' },
  { to: '/evaluate', icon: <FlaskConical size={16} />, label: 'Evaluation' },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--background)' }}>
      {/* Sidebar */}
      <aside style={{
        width: 220, flexShrink: 0, background: '#0d1117',
        display: 'flex', flexDirection: 'column', height: '100%',
      }}>
        {/* Logo */}
        <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, background: '#156235', borderRadius: 8,
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Sprout size={16} color="white" />
            </div>
            <div>
              <div style={{ color: 'white', fontWeight: 700, fontSize: 15, lineHeight: 1 }}>ReliefTrace</div>
              <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10, fontFamily: 'DM Mono, monospace', marginTop: 3 }}>
                Evidence Verification
              </div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflowY: 'auto', padding: '12px 8px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {NAV.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                style={({ isActive }) => ({
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '8px 12px', borderRadius: 6, fontSize: 13, fontWeight: 500,
                  textDecoration: 'none', transition: 'all 0.15s',
                  background: isActive ? '#156235' : 'transparent',
                  color: isActive ? 'white' : 'rgba(255,255,255,0.5)',
                })}
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>

        {/* Footer */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', lineHeight: 1.5 }}>
            <div>Independent-evidence verification</div>
            <div style={{ marginTop: 2, color: 'rgba(255,255,255,0.2)' }}>
              AI supports human decisions only
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Top bar */}
        <header style={{
          height: 52, background: 'white', borderBottom: '1px solid #e2e8f0',
          display: 'flex', alignItems: 'center', padding: '0 24px',
          flexShrink: 0,
        }}>
          <div style={{ flex: 1 }} />
          <div style={{
            fontSize: 11, color: '#94a3b8', background: '#f8fafc',
            border: '1px solid #e2e8f0', borderRadius: 4, padding: '3px 8px',
            fontFamily: 'DM Mono, monospace',
          }}>
            AI ≠ Decision — Human reviewer decides
          </div>
        </header>

        {/* Page */}
        <main style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
          {children}
        </main>
      </div>
    </div>
  );
}
