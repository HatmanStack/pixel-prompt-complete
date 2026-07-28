/**
 * useGallery tests.
 *
 * The hook asks for a bounded page rather than "everything". The backend
 * clamps independently, so these pin the request the client makes; they are
 * not evidence of the server-side bound, which lives in
 * tests/backend/unit/test_lambda_function.py.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const listSessionsMock = vi.fn();
const getSessionDetailMock = vi.fn();

vi.mock('../../../src/api/client', () => ({
  listSessions: (limit?: number, cursor?: string) => listSessionsMock(limit, cursor),
  getSessionDetail: (id: string) => getSessionDetailMock(id),
}));

import useGallery from '../../../src/hooks/useGallery';

describe('useGallery', () => {
  beforeEach(() => {
    listSessionsMock.mockReset();
    getSessionDetailMock.mockReset();
    listSessionsMock.mockResolvedValue({ galleries: [], total: 0 });
  });

  it('asks for a bounded page rather than every gallery', async () => {
    renderHook(() => useGallery());

    await waitFor(() => expect(listSessionsMock).toHaveBeenCalled());
    expect(listSessionsMock).toHaveBeenCalledWith(20, undefined);
  });

  it('maps the returned galleries onto items with preview URLs', async () => {
    listSessionsMock.mockResolvedValue({
      galleries: [
        {
          id: '2026-01-01-00-00-01',
          timestamp: '2026-01-01T00:00:01Z',
          imageCount: 4,
          previewUrl: 'https://cdn/p.png',
        },
      ],
      total: 1,
    });

    const { result } = renderHook(() => useGallery());

    await waitFor(() => expect(result.current.galleries).toHaveLength(1));
    expect(result.current.galleries[0]).toMatchObject({
      id: '2026-01-01-00-00-01',
      imageCount: 4,
      previewUrl: 'https://cdn/p.png',
      preview: 'https://cdn/p.png',
    });
    expect(result.current.error).toBeNull();
  });

  it('surfaces a failure instead of leaving stale galleries on screen', async () => {
    listSessionsMock.mockRejectedValue(new Error('gateway timeout'));

    const { result } = renderHook(() => useGallery());

    await waitFor(() => expect(result.current.error).toBe('gateway timeout'));
    expect(result.current.galleries).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});

describe('useGallery pagination', () => {
  beforeEach(() => {
    listSessionsMock.mockReset();
    getSessionDetailMock.mockReset();
  });

  const page = (ids: string[], nextCursor?: string) => ({
    galleries: ids.map((id) => ({
      id,
      timestamp: `${id}T00:00:00Z`,
      imageCount: 1,
      previewUrl: `https://cdn.test/${id}.png`,
    })),
    total: ids.length,
    ...(nextCursor ? { nextCursor } : {}),
  });

  it('reports more available when the response carries a cursor', async () => {
    listSessionsMock.mockResolvedValue(page(['g1'], 'g1'));

    const { result } = renderHook(() => useGallery());

    await waitFor(() => expect(result.current.galleries).toHaveLength(1));
    expect(result.current.hasMore).toBe(true);
  });

  it('reports no more available when the cursor is absent', async () => {
    listSessionsMock.mockResolvedValue(page(['g1']));

    const { result } = renderHook(() => useGallery());

    await waitFor(() => expect(result.current.galleries).toHaveLength(1));
    expect(result.current.hasMore).toBe(false);
  });

  it('appends the next page and forwards the cursor it was given', async () => {
    // The regression: the backend paginates, and dropping nextCursor made
    // every gallery past the first page unreachable from the app.
    listSessionsMock.mockResolvedValueOnce(page(['g2'], 'g2'));
    const { result } = renderHook(() => useGallery());
    await waitFor(() => expect(result.current.galleries).toHaveLength(1));

    listSessionsMock.mockResolvedValueOnce(page(['g1']));
    await result.current.loadMore();

    await waitFor(() => expect(result.current.galleries).toHaveLength(2));
    expect(listSessionsMock).toHaveBeenLastCalledWith(20, 'g2');
    expect(result.current.galleries.map((g) => g.id)).toEqual(['g2', 'g1']);
    expect(result.current.hasMore).toBe(false);
  });

  it('does not render a gallery twice if a page overlaps', async () => {
    listSessionsMock.mockResolvedValueOnce(page(['g2'], 'g2'));
    const { result } = renderHook(() => useGallery());
    await waitFor(() => expect(result.current.galleries).toHaveLength(1));

    listSessionsMock.mockResolvedValueOnce(page(['g2', 'g1']));
    await result.current.loadMore();

    await waitFor(() => expect(result.current.hasMore).toBe(false));
    expect(result.current.galleries.map((g) => g.id)).toEqual(['g2', 'g1']);
  });

  it('keeps the cursor when a page fails so the user can retry', async () => {
    listSessionsMock.mockResolvedValueOnce(page(['g2'], 'g2'));
    const { result } = renderHook(() => useGallery());
    await waitFor(() => expect(result.current.galleries).toHaveLength(1));

    listSessionsMock.mockRejectedValueOnce(new Error('network'));
    await result.current.loadMore();

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.hasMore).toBe(true);
  });

  it('does not fetch when there is no cursor', async () => {
    listSessionsMock.mockResolvedValue(page(['g1']));
    const { result } = renderHook(() => useGallery());
    await waitFor(() => expect(result.current.galleries).toHaveLength(1));
    listSessionsMock.mockClear();

    await result.current.loadMore();

    expect(listSessionsMock).not.toHaveBeenCalled();
  });
});
