/**
 * Tests for useBreakpoint hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBreakpoint } from '../../../src/hooks/useBreakpoint';

describe('useBreakpoint', () => {
  let listeners: Map<string, Set<(e: MediaQueryListEvent) => void>>;

  beforeEach(() => {
    listeners = new Map();

    const mockMatchMedia = (query: string): MediaQueryList => {
      const listenerSet = new Set<(e: MediaQueryListEvent) => void>();
      listeners.set(query, listenerSet);

      return {
        matches: false,
        media: query,
        onchange: null,
        addEventListener: (
          _type: string,
          listener: EventListenerOrEventListenerObject
        ) => {
          listenerSet.add(listener as (e: MediaQueryListEvent) => void);
        },
        removeEventListener: (
          _type: string,
          listener: EventListenerOrEventListenerObject
        ) => {
          listenerSet.delete(listener as (e: MediaQueryListEvent) => void);
        },
        dispatchEvent: () => true,
        addListener: vi.fn(),
        removeListener: vi.fn(),
      };
    };

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: mockMatchMedia,
    });

    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      value: 1024,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns lg breakpoint for 1024px width', () => {
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    const { result } = renderHook(() => useBreakpoint());

    expect(result.current.breakpoint).toBe('lg');
    expect(result.current.isDesktop).toBe(true);
    expect(result.current.isMobile).toBe(false);
  });

  it('returns sm breakpoint for small width', () => {
    Object.defineProperty(window, 'innerWidth', { value: 400, writable: true });
    const { result } = renderHook(() => useBreakpoint());

    expect(result.current.breakpoint).toBe('sm');
    expect(result.current.isSmall).toBe(true);
    expect(result.current.isMobile).toBe(true);
    expect(result.current.isDesktop).toBe(false);
  });

  it('returns xl breakpoint for large width', () => {
    Object.defineProperty(window, 'innerWidth', { value: 1400, writable: true });
    const { result } = renderHook(() => useBreakpoint());

    expect(result.current.breakpoint).toBe('xl');
    expect(result.current.isExtraLarge).toBe(true);
    expect(result.current.isDesktop).toBe(true);
  });

  it('returns md breakpoint for medium width', () => {
    Object.defineProperty(window, 'innerWidth', { value: 800, writable: true });
    const { result } = renderHook(() => useBreakpoint());

    expect(result.current.breakpoint).toBe('md');
    expect(result.current.isMedium).toBe(true);
    expect(result.current.isMobile).toBe(true);
  });

  it('updates breakpoint on resize', () => {
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    const { result } = renderHook(() => useBreakpoint());

    expect(result.current.breakpoint).toBe('lg');

    // Simulate resize
    act(() => {
      Object.defineProperty(window, 'innerWidth', { value: 500, writable: true });
      // Trigger listeners
      listeners.forEach((listenerSet) => {
        listenerSet.forEach((listener) => {
          listener({ matches: false } as MediaQueryListEvent);
        });
      });
    });

    expect(result.current.breakpoint).toBe('sm');
  });

  it('cleans up listeners on unmount', () => {
    const { unmount } = renderHook(() => useBreakpoint());

    // Listeners should exist
    expect(listeners.size).toBeGreaterThan(0);

    unmount();

    // All listener sets should be empty after cleanup
    listeners.forEach((listenerSet) => {
      expect(listenerSet.size).toBe(0);
    });
  });
});
