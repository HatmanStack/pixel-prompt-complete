/**
 * Session Polling Hook
 * Polls session status and updates store progressively
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { getSessionStatus } from '@/api/client';
import { useAppStore } from '@/stores/useAppStore';

const DEFAULT_INTERVAL_MS = 2000;
const MAX_CONSECUTIVE_ERRORS = 5;
const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

interface UseSessionPollingOptions {
  intervalMs?: number;
  enabled?: boolean;
}

interface UseSessionPollingResult {
  error: string | null;
  isPolling: boolean;
}

export function useSessionPolling(
  sessionId: string | null,
  options: UseSessionPollingOptions = {}
): UseSessionPollingResult {
  const { intervalMs = DEFAULT_INTERVAL_MS, enabled = true } = options;

  const { setCurrentSession, setIsGenerating } = useAppStore();
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Use refs to avoid stale closures
  const mountedRef = useRef(true);
  const consecutiveErrorsRef = useRef(0);
  const startTimeRef = useRef<number | null>(null);
  const timeoutIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
    setIsGenerating(false);
    if (timeoutIdRef.current) {
      clearTimeout(timeoutIdRef.current);
      timeoutIdRef.current = null;
    }
  }, [setIsGenerating]);

  const poll = useCallback(async () => {
    if (!mountedRef.current || !sessionId) return;

    // Check for timeout
    if (startTimeRef.current && Date.now() - startTimeRef.current > TIMEOUT_MS) {
      setError('Session timed out after 5 minutes');
      stopPolling();
      return;
    }

    try {
      const session = await getSessionStatus(sessionId);
      if (!mountedRef.current) return;

      setCurrentSession(session);
      consecutiveErrorsRef.current = 0;
      setError(null);

      // Check if complete
      if (['completed', 'partial', 'failed'].includes(session.status)) {
        stopPolling();
        return;
      }

      // Continue polling
      timeoutIdRef.current = setTimeout(poll, intervalMs);
    } catch (err) {
      if (!mountedRef.current) return;

      consecutiveErrorsRef.current++;

      if (consecutiveErrorsRef.current >= MAX_CONSECUTIVE_ERRORS) {
        setError('Failed to get status after multiple attempts');
        stopPolling();
        return;
      }

      // Exponential backoff
      const backoffDelay = intervalMs * Math.pow(2, consecutiveErrorsRef.current);
      timeoutIdRef.current = setTimeout(poll, backoffDelay);
    }
  }, [sessionId, intervalMs, setCurrentSession, stopPolling]);

  useEffect(() => {
    mountedRef.current = true;

    if (!sessionId || !enabled) {
      setIsPolling(false);
      return;
    }

    // Start polling
    setIsPolling(true);
    setError(null);
    consecutiveErrorsRef.current = 0;
    startTimeRef.current = Date.now();
    poll();

    return () => {
      mountedRef.current = false;
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
        timeoutIdRef.current = null;
      }
    };
  }, [sessionId, enabled, poll]);

  return { error, isPolling };
}
