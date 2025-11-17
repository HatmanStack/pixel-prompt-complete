/**
 * useJobPolling Hook
 * Polls job status at regular intervals until completion
 */

import { useState, useEffect, useRef } from 'react';
import { getJobStatus } from '../api/client';

// Polling configuration
const DEFAULT_INTERVAL = 2000; // 2 seconds
const TIMEOUT_DURATION = 300000; // 5 minutes
const MAX_CONSECUTIVE_ERRORS = 5;

/**
 * Custom hook for polling job status
 * @param {string} jobId - The job ID to poll
 * @param {number} interval - Polling interval in milliseconds
 * @returns {Object} { jobStatus, isPolling, error }
 */
function useJobPolling(jobId, interval = DEFAULT_INTERVAL) {
  const [jobStatus, setJobStatus] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);

  const pollingTimeoutRef = useRef(null);
  const startTimeRef = useRef(null);
  const consecutiveErrorsRef = useRef(0);
  const isMountedRef = useRef(true);

  useEffect(() => {
    // Reset mounted flag
    isMountedRef.current = true;

    // Reset state when jobId changes
    if (!jobId) {
      setJobStatus(null);
      setIsPolling(false);
      setError(null);
      return;
    }

    // Start polling
    setIsPolling(true);
    setError(null);
    startTimeRef.current = Date.now();
    consecutiveErrorsRef.current = 0;

    const pollStatus = async () => {
      // Skip if component unmounted or jobId changed
      if (!isMountedRef.current) {
        return;
      }

      try {
        // Check for timeout (5 minutes)
        const elapsed = Date.now() - startTimeRef.current;
        if (elapsed > TIMEOUT_DURATION) {
          setError('Job polling timed out after 5 minutes');
          setIsPolling(false);
          return;
        }

        // Fetch job status
        const status = await getJobStatus(jobId);

        // Check again if still mounted
        if (!isMountedRef.current) {
          return;
        }

        setJobStatus(status);

        // Reset consecutive errors on success
        consecutiveErrorsRef.current = 0;

        // Stop polling if job is complete, partial, or failed
        if (status.status === 'completed' || status.status === 'partial' || status.status === 'failed') {
          setIsPolling(false);
          return;
        }

        // Schedule next poll with default interval
        pollingTimeoutRef.current = setTimeout(pollStatus, interval);
      } catch (err) {
        console.error('Error polling job status:', err);

        // Skip if component unmounted
        if (!isMountedRef.current) {
          return;
        }

        // Increment consecutive errors
        consecutiveErrorsRef.current += 1;

        // Exponential backoff for errors
        if (consecutiveErrorsRef.current <= MAX_CONSECUTIVE_ERRORS) {
          const backoffInterval = Math.min(
            interval * Math.pow(2, consecutiveErrorsRef.current - 1),
            8000 // Max 8 seconds
          );

          // Schedule next poll with backoff
          pollingTimeoutRef.current = setTimeout(pollStatus, backoffInterval);
        } else {
          // Stop polling after max consecutive errors
          setError(`Failed to fetch job status after ${MAX_CONSECUTIVE_ERRORS} attempts`);
          setIsPolling(false);
        }
      }
    };

    // Start polling
    pollStatus();

    // Cleanup on unmount or when jobId changes
    return () => {
      isMountedRef.current = false;
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
      }
      setIsPolling(false);
    };
  }, [jobId, interval]);

  return {
    jobStatus,
    isPolling,
    error,
  };
}

export default useJobPolling;
