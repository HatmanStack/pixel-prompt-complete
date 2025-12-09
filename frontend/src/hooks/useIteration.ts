/**
 * Iteration Hooks
 * Manage iteration logic including limit checking and API calls
 */

import { useCallback } from 'react';
import { iterateImage, iterateMultiple } from '@/api/client';
import { useAppStore } from '@/stores/useAppStore';
import type { ModelName } from '@/types';

export const MAX_ITERATIONS = 7;
export const WARNING_THRESHOLD = 5;

interface UseIterationResult {
  iterate: (prompt: string) => Promise<void>;
  iterationCount: number;
  isAtLimit: boolean;
  showWarning: boolean;
  remainingIterations: number;
  isEnabled: boolean;
}

/**
 * Hook for managing iteration on a single model
 */
export function useIteration(model: ModelName): UseIterationResult {
  const {
    currentSession,
    checkIterationWarning,
    iterationWarnings,
  } = useAppStore();

  const column = currentSession?.models[model];
  const iterationCount = column?.iterations.length ?? 0;
  const isAtLimit = iterationCount >= MAX_ITERATIONS;
  const showWarning = iterationWarnings[model] || iterationCount >= WARNING_THRESHOLD;
  const isEnabled = column?.enabled ?? false;

  const iterate = useCallback(
    async (prompt: string): Promise<void> => {
      if (!currentSession || isAtLimit || !isEnabled) {
        return;
      }

      try {
        await iterateImage(currentSession.sessionId, model, prompt);
        checkIterationWarning(model);
      } catch (err) {
        console.error(`Failed to iterate on ${model}:`, err);
        throw err;
      }
    },
    [currentSession, model, isAtLimit, isEnabled, checkIterationWarning]
  );

  return {
    iterate,
    iterationCount,
    isAtLimit,
    showWarning,
    remainingIterations: Math.max(0, MAX_ITERATIONS - iterationCount),
    isEnabled,
  };
}

interface UseMultiIterateResult {
  iterateSelected: (prompt: string) => Promise<void>;
  selectedCount: number;
  canIterate: boolean;
}

/**
 * Hook for managing iteration on multiple selected models
 */
export function useMultiIterate(): UseMultiIterateResult {
  const { currentSession, selectedModels, clearSelection } = useAppStore();

  const canIterate = currentSession !== null && selectedModels.size > 0;

  const iterateSelected = useCallback(
    async (prompt: string): Promise<void> => {
      if (!currentSession || selectedModels.size === 0) {
        return;
      }

      const models = Array.from(selectedModels);

      try {
        await iterateMultiple(currentSession.sessionId, models, prompt);
        clearSelection();
      } catch (err) {
        console.error('Failed to iterate on selected models:', err);
        throw err;
      }
    },
    [currentSession, selectedModels, clearSelection]
  );

  return {
    iterateSelected,
    selectedCount: selectedModels.size,
    canIterate,
  };
}

/**
 * Utility to check if a model can accept more iterations
 */
export function canModelIterate(
  currentSession: ReturnType<typeof useAppStore.getState>['currentSession'],
  model: ModelName
): boolean {
  if (!currentSession) return false;

  const column = currentSession.models[model];
  if (!column || !column.enabled) return false;

  return column.iterations.length < MAX_ITERATIONS;
}

/**
 * Get iteration status for a model
 */
export function getIterationStatus(
  currentSession: ReturnType<typeof useAppStore.getState>['currentSession'],
  model: ModelName
): {
  count: number;
  remaining: number;
  isAtLimit: boolean;
  showWarning: boolean;
} {
  if (!currentSession) {
    return { count: 0, remaining: MAX_ITERATIONS, isAtLimit: false, showWarning: false };
  }

  const column = currentSession.models[model];
  const count = column?.iterations.length ?? 0;
  const remaining = Math.max(0, MAX_ITERATIONS - count);

  return {
    count,
    remaining,
    isAtLimit: count >= MAX_ITERATIONS,
    showWarning: count >= WARNING_THRESHOLD,
  };
}
