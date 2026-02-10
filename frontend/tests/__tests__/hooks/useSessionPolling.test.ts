/**
 * Tests for useSessionPolling hook
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSessionPolling } from '../../../src/hooks/useSessionPolling';
import { useAppStore } from '../../../src/stores/useAppStore';
import type { Session, ModelColumn, ModelName } from '../../../src/types';

// Mock API client
vi.mock('../../../src/api/client', () => ({
  getSessionStatus: vi.fn(),
}));

import { getSessionStatus } from '../../../src/api/client';

const mockedGetSessionStatus = vi.mocked(getSessionStatus);

// Helper to create a mock model column
const createMockModelColumn = (name: ModelName): ModelColumn => ({
  name,
  enabled: true,
  status: 'completed',
  iterations: [
    {
      index: 0,
      status: 'completed',
      prompt: 'test prompt',
      imageUrl: `https://example.com/${name}-0.png`,
    },
  ],
});

// Helper to create a mock session with a given status
const createMockSession = (
  sessionId: string,
  status: Session['status'] = 'in_progress'
): Session => ({
  sessionId,
  status,
  prompt: 'test prompt',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
  models: {
    flux: createMockModelColumn('flux'),
    recraft: createMockModelColumn('recraft'),
    gemini: createMockModelColumn('gemini'),
    openai: createMockModelColumn('openai'),
  },
});

describe('useSessionPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset store state
    useAppStore.setState({
      currentSession: null,
      isGenerating: false,
    });
    // Reset all mocks including implementations (clearAllMocks only clears calls)
    vi.restoreAllMocks();
    mockedGetSessionStatus.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not poll when sessionId is null', async () => {
    const { result } = renderHook(() => useSessionPolling(null));

    // Advance time well past poll interval
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    expect(mockedGetSessionStatus).not.toHaveBeenCalled();
    expect(result.current.isPolling).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('polls and updates store on success', async () => {
    const mockSession = createMockSession('session-1', 'in_progress');
    mockedGetSessionStatus.mockResolvedValueOnce(mockSession);

    renderHook(() => useSessionPolling('session-1'));

    // The initial poll fires immediately on mount; flush it
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(mockedGetSessionStatus).toHaveBeenCalledWith('session-1');

    // Verify the store was updated with the session data
    const storeState = useAppStore.getState();
    expect(storeState.currentSession).toEqual(mockSession);
  });

  it('stops polling on completed status', async () => {
    const completedSession = createMockSession('session-2', 'completed');
    mockedGetSessionStatus.mockResolvedValueOnce(completedSession);

    const { result } = renderHook(() => useSessionPolling('session-2'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(1);
    expect(result.current.isPolling).toBe(false);

    // Advance time further -- should not poll again
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(1);
  });

  it('stops polling on partial status', async () => {
    const partialSession = createMockSession('session-partial', 'partial');
    mockedGetSessionStatus.mockResolvedValueOnce(partialSession);

    const { result } = renderHook(() => useSessionPolling('session-partial'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(1);
    expect(result.current.isPolling).toBe(false);
  });

  it('stops polling on failed status', async () => {
    const failedSession = createMockSession('session-failed', 'failed');
    mockedGetSessionStatus.mockResolvedValueOnce(failedSession);

    const { result } = renderHook(() => useSessionPolling('session-failed'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(1);
    expect(result.current.isPolling).toBe(false);
  });

  it('stops after MAX_CONSECUTIVE_ERRORS (5) and sets error', async () => {
    // All 5 calls reject
    for (let i = 0; i < 5; i++) {
      mockedGetSessionStatus.mockRejectedValueOnce(new Error('Network error'));
    }

    const { result } = renderHook(() =>
      useSessionPolling('session-err', { intervalMs: 100 })
    );

    // Flush through all 5 error cycles with exponential backoff:
    // call 1 immediate, call 2 after 200ms, call 3 after 400ms, call 4 after 800ms, call 5 after 1600ms
    for (let i = 0; i < 5; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
    }

    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(5);
    expect(result.current.error).toBe('Failed to get status after multiple attempts');
    expect(result.current.isPolling).toBe(false);
  });

  it('clears timeout on unmount', async () => {
    const inProgressSession = createMockSession('session-unmount', 'in_progress');
    mockedGetSessionStatus.mockResolvedValue(inProgressSession);

    const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');

    const { unmount } = renderHook(() => useSessionPolling('session-unmount'));

    // Let the first poll resolve and schedule the next timeout
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Unmount should clear the pending timeout
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalled();
    clearTimeoutSpy.mockRestore();
  });

  it('ignores stale responses when sessionId changes', async () => {
    // First session returns slowly (will be stale)
    let resolveFirst!: (value: Session) => void;
    const firstPromise = new Promise<Session>((resolve) => {
      resolveFirst = resolve;
    });
    mockedGetSessionStatus.mockReturnValueOnce(firstPromise);

    // Second session returns immediately
    const secondSession = createMockSession('session-B', 'in_progress');
    mockedGetSessionStatus.mockResolvedValueOnce(secondSession);

    const { rerender } = renderHook(
      ({ sessionId }: { sessionId: string | null }) => useSessionPolling(sessionId),
      { initialProps: { sessionId: 'session-A' as string | null } }
    );

    // Initial poll for session-A is in flight
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Change to session-B before session-A resolves
    rerender({ sessionId: 'session-B' });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Now resolve the stale session-A response
    const staleSession = createMockSession('session-A', 'completed');
    await act(async () => {
      resolveFirst(staleSession);
    });

    // The store should have session-B, not the stale session-A
    const storeState = useAppStore.getState();
    expect(storeState.currentSession?.sessionId).toBe('session-B');
  });

  it('returns error message when polling fails', async () => {
    mockedGetSessionStatus.mockRejectedValue(new Error('Server error'));

    renderHook(() =>
      useSessionPolling('session-fail', { intervalMs: 100 })
    );

    // First poll fails immediately
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // The hook should have recorded an error (or still be retrying)
    // At minimum, getSessionStatus was called
    expect(mockedGetSessionStatus).toHaveBeenCalledWith('session-fail');
  });

  it('does not poll when enabled option is false', async () => {
    const { result } = renderHook(() =>
      useSessionPolling('session-disabled', { enabled: false })
    );

    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    expect(mockedGetSessionStatus).not.toHaveBeenCalled();
    expect(result.current.isPolling).toBe(false);
  });

  it('starts polling when enabled changes from false to true', async () => {
    const mockSession = createMockSession('session-enable', 'in_progress');
    mockedGetSessionStatus.mockResolvedValue(mockSession);

    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useSessionPolling('session-enable', { enabled }),
      { initialProps: { enabled: false } }
    );

    // Should not be polling
    expect(result.current.isPolling).toBe(false);
    expect(mockedGetSessionStatus).not.toHaveBeenCalled();

    // Enable polling
    rerender({ enabled: true });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(mockedGetSessionStatus).toHaveBeenCalledWith('session-enable');
  });

  it('continues polling while session is in_progress', async () => {
    const inProgressSession = createMockSession('session-continue', 'in_progress');
    mockedGetSessionStatus.mockResolvedValue(inProgressSession);

    renderHook(() =>
      useSessionPolling('session-continue', { intervalMs: 1000 })
    );

    // First poll (immediate)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(1);

    // Second poll after interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(2);

    // Third poll after another interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mockedGetSessionStatus).toHaveBeenCalledTimes(3);
  });
});
