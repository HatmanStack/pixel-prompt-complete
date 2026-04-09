/**
 * useMePolling tests.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

const refreshMock = vi.fn();

vi.mock('../../../src/stores/useBillingStore', () => ({
  useBillingStore: (selector: (s: { refresh: () => void }) => unknown) =>
    selector({ refresh: refreshMock }),
}));

let isAuthed = true;
vi.mock('../../../src/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: { isAuthenticated: () => boolean }) => unknown) =>
    selector({ isAuthenticated: () => isAuthed }),
}));

let currentSession: unknown = null;
vi.mock('../../../src/stores/useAppStore', () => ({
  useAppStore: (selector: (s: { currentSession: unknown }) => unknown) =>
    selector({ currentSession }),
}));

import { useMePolling } from '../../../src/hooks/useMePolling';

describe('useMePolling', () => {
  beforeEach(() => {
    refreshMock.mockReset();
    isAuthed = true;
    currentSession = null;
  });

  it('refreshes on mount when authenticated', () => {
    renderHook(() => useMePolling());
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });

  it('does not refresh when signed out', () => {
    isAuthed = false;
    renderHook(() => useMePolling());
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it('refreshes again when session changes', () => {
    const { rerender } = renderHook(() => useMePolling());
    expect(refreshMock).toHaveBeenCalledTimes(1);
    currentSession = { sessionId: 'new' };
    rerender();
    expect(refreshMock).toHaveBeenCalledTimes(2);
  });
});
