import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { Dashboard } from './pages/Dashboard';
import { SubmitClaim } from './pages/SubmitClaim';
import { InvestigationWorkspace } from './pages/InvestigationWorkspace';
import { EvaluationPage } from './pages/EvaluationPage';

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/submit" element={<SubmitClaim />} />
          <Route path="/claims/:claimId" element={<InvestigationWorkspace />} />
          <Route path="/evaluate" element={<EvaluationPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
