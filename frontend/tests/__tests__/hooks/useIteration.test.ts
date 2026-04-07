/**
 * Tests for useIteration hook
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useIteration, useMultiIterate } from '../../../src/hooks/useIteration';
import { MAX_ITERATIONS, WARNING_THRESHOLD } from '../../../src/config/constants';
import { useAppStore } from '../../../src/stores/useAppStore';
import type { Session, ModelColumn, Iteration, ModelName } from '../../../src/types';

// Mock API client
vi.mock('../../../src/api/client', () => ({
  iterateImage: vi.fn().mockResolvedValue({ sessionId: 'test', model: 'gemini', iteration: 1, status: 'success' }),
  iterateMultiple: vi.fn().mockResolvedValue([{ sessionId: 'test', model: 'gemini', iteration: 1, status: 'success' }]),
}));

// Helper to create mock iteration
const createMockIteration = (index: number): Iteration => ({
  index,
  status: 'completed',
  prompt: `iteration ${index}`,
  imageUrl: `https://example.com/image-${index}.png`,
});

// Helper to create mock model column
const createMockModelColumn = (name: ModelName, iterationCount = 0, enabled = true): ModelColumn => ({
  name,
  enabled,
  status: 'completed',
  iterations: Array.from({ length: iterationCount }, (_, i) => createMockIteration(i)),
});

// Helper to create mock session
const createMockSession = (
  geminiIterations = 0,
  geminiEnabled = true
): Session => ({
  sessionId: 'test-session',
  status: 'completed',
  prompt: 'test prompt',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
  models: {
    gemini: createMockModelColumn('gemini', geminiIterations, geminiEnabled),
    nova: createMockModelColumn('nova', 0, true),
    openai: createMockModelColumn('openai', 0, true),
    firefly: createMockModelColumn('firefly', 0, true),
  },
});

describe('useIteration', () => {
  beforeEach(() => {
    // Reset store
    useAppStore.setState({
      currentSession: null,
      selectedModels: new Set(),
      isMultiSelectMode: false,
      iterationWarnings: {
        gemini: false,
        nova: false,
        openai: false,
        firefly: false,
      },
    });
    vi.clearAllMocks();
  });

  describe('iteration count', () => {
    it('returns 0 when no session', () => {
      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.iterationCount).toBe(0);
    });

    it('returns correct count when session has iterations', () => {
      useAppStore.setState({ currentSession: createMockSession(3) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.iterationCount).toBe(3);
    });
  });

  describe('isAtLimit', () => {
    it('returns false when below limit', () => {
      useAppStore.setState({ currentSession: createMockSession(5) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.isAtLimit).toBe(false);
    });

    it('returns true when at limit', () => {
      useAppStore.setState({ currentSession: createMockSession(MAX_ITERATIONS) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.isAtLimit).toBe(true);
    });
  });

  describe('showWarning', () => {
    it('returns false when below threshold', () => {
      useAppStore.setState({ currentSession: createMockSession(3) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.showWarning).toBe(false);
    });

    it('returns true when at or above threshold', () => {
      useAppStore.setState({ currentSession: createMockSession(WARNING_THRESHOLD) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.showWarning).toBe(true);
    });

    it('returns true when warning flag is set', () => {
      useAppStore.setState({
        currentSession: createMockSession(3),
        iterationWarnings: { gemini: true, nova: false, openai: false, firefly: false },
      });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.showWarning).toBe(true);
    });
  });

  describe('remainingIterations', () => {
    it('calculates remaining correctly', () => {
      useAppStore.setState({ currentSession: createMockSession(3) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.remainingIterations).toBe(MAX_ITERATIONS - 3);
    });

    it('returns 0 when at limit', () => {
      useAppStore.setState({ currentSession: createMockSession(MAX_ITERATIONS) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.remainingIterations).toBe(0);
    });
  });

  describe('isEnabled', () => {
    it('returns true when model is enabled', () => {
      useAppStore.setState({ currentSession: createMockSession(0, true) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.isEnabled).toBe(true);
    });

    it('returns false when model is disabled', () => {
      useAppStore.setState({ currentSession: createMockSession(0, false) });

      const { result } = renderHook(() => useIteration('gemini'));

      expect(result.current.isEnabled).toBe(false);
    });
  });
});

describe('useMultiIterate', () => {
  beforeEach(() => {
    useAppStore.setState({
      currentSession: createMockSession(),
      selectedModels: new Set(),
      isMultiSelectMode: false,
    });
    vi.clearAllMocks();
  });

  describe('selectedCount', () => {
    it('returns 0 when no models selected', () => {
      const { result } = renderHook(() => useMultiIterate());

      expect(result.current.selectedCount).toBe(0);
    });

    it('returns correct count when models selected', () => {
      useAppStore.setState({ selectedModels: new Set(['gemini', 'nova']) });

      const { result } = renderHook(() => useMultiIterate());

      expect(result.current.selectedCount).toBe(2);
    });
  });

  describe('canIterate', () => {
    it('returns false when no session', () => {
      useAppStore.setState({
        currentSession: null,
        selectedModels: new Set(['gemini']),
      });

      const { result } = renderHook(() => useMultiIterate());

      expect(result.current.canIterate).toBe(false);
    });

    it('returns false when no models selected', () => {
      useAppStore.setState({
        currentSession: createMockSession(),
        selectedModels: new Set(),
      });

      const { result } = renderHook(() => useMultiIterate());

      expect(result.current.canIterate).toBe(false);
    });

    it('returns true when session exists and models selected', () => {
      useAppStore.setState({
        currentSession: createMockSession(),
        selectedModels: new Set(['gemini', 'nova']),
      });

      const { result } = renderHook(() => useMultiIterate());

      expect(result.current.canIterate).toBe(true);
    });
  });
});
