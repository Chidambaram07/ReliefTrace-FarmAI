/**
 * React hooks for fetching real data from the ReliefTrace backend.
 * Used by all portals instead of static SAMPLE_CLAIMS / SAMPLE_OFFICERS.
 */
import { useState, useEffect, useCallback } from 'react';
import { api, BackendStats, ReviewQueueItem, AgenticResult } from './api';
import { fetchClaims, fetchStats, fetchReviewQueue, computeDistrictStats } from './data';
import type { Claim, DistrictStats } from './types';

/** Load all claims from the backend. Returns { claims, loading, error, refresh }. */
export function useClaims() {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchClaims();
      setClaims(data);
    } catch (e: any) {
      setError(e.message || 'Failed to load claims');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  return { claims, loading, error, refresh };
}

/** Load backend stats. */
export function useStats() {
  const [stats, setStats] = useState<BackendStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats().then(s => { setStats(s); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  return { stats, loading };
}

/** Load the review queue. */
export function useReviewQueue(status = 'open') {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchReviewQueue(status);
      setItems(r.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { refresh(); }, [refresh]);
  return { items, loading, refresh };
}

/** Compute district stats from loaded claims. */
export function useDistrictStats(claims: Claim[]): DistrictStats[] {
  return computeDistrictStats(claims);
}

/** Run MVP verification on a claim. */
export function useVerification() {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const verify = useCallback(async (claimId: string) => {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const r = await api.verify(claimId);
      setReport(r);
    } catch (e: any) {
      setError(e.message || 'Verification failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return { verify, report, loading, error };
}

/** Run agentic verification on a claim. */
export function useAgenticVerification() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgenticResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const verify = useCallback(async (claimId: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.verifyAgentic(claimId);
      setResult(r);
    } catch (e: any) {
      setError(e.message || 'Agentic verification failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return { verify, result, loading, error };
}

/** Backend health check. */
export function useHealth() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.health().then(h => { setHealth(h); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  return { health, loading };
}
