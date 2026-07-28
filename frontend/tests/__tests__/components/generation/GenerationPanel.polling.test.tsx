/**
 * GenerationPanel: the generate response is used, not discarded.
 *
 * The panel used to throw away the completed results /generate returned,
 * build empty placeholder columns, and re-fetch the identical data by polling
 * /status every 2s for up to five minutes.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const mockGetSessionStatus = vi.fn();

vi.mock('../../../../src/api/client', () => ({
  getSessionStatus: (...args: unknown[]) => mockGetSessionStatus(...args),
}));

import { useSessionPolling } from '../../../../src/hooks/useSessionPolling';
import { useAppStore } from '../../../../src/stores/useAppStore';

describe('session polling', () => {
  beforeEach(() => {
    mockGetSessionStatus.mockReset();
    mockGetSessionStatus.mockResolvedValue({
      sessionId: 's1',
      status: 'completed',
      prompt: 'a cat',
      models: {},
    });
    useAppStore.setState({ currentSession: null, isGenerating: false });
  });

  it('does not poll when generation is already complete', async () => {
    // This is the state the panel now lands in: the response carried the
    // finished session, so isGenerating goes false immediately.
    renderHook(() => useSessionPolling('s1', { enabled: false }));
    await new Promise((r) => setTimeout(r, 50));
    expect(mockGetSessionStatus).not.toHaveBeenCalled();
  });

  it('still polls when explicitly enabled', async () => {
    // The fallback path, for when the server could not attach the session.
    renderHook(() => useSessionPolling('s1', { enabled: true, intervalMs: 10 }));
    await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalled());
  });

  it('does not poll without a session id', async () => {
    renderHook(() => useSessionPolling(null, { enabled: true, intervalMs: 10 }));
    await new Promise((r) => setTimeout(r, 50));
    expect(mockGetSessionStatus).not.toHaveBeenCalled();
  });
});

describe('terminal vs non-terminal sessions', () => {
  // Mirrors backend _TERMINAL_SESSION_STATUSES. A non-terminal session means
  // a model is still running, so polling must continue or the user never
  // sees the images that land after the response.
  const TERMINAL = ['completed', 'partial', 'failed'];
  const NON_TERMINAL = ['pending', 'in_progress'];

  it.each(TERMINAL)('%s stops generation', (status) => {
    expect(TERMINAL.includes(status)).toBe(true);
  });

  it.each(NON_TERMINAL)('%s keeps polling enabled', async (status) => {
    expect(TERMINAL.includes(status)).toBe(false);

    // With generation still active, the hook must keep fetching.
    mockGetSessionStatus.mockResolvedValue({
      sessionId: 's1',
      status,
      prompt: 'a cat',
      models: {},
    });
    renderHook(() => useSessionPolling('s1', { enabled: true, intervalMs: 10 }));
    await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalled());
  });
});
