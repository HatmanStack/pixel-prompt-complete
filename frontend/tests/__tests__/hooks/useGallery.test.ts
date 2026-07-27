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
  listSessions: (limit?: number) => listSessionsMock(limit),
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
    expect(listSessionsMock).toHaveBeenCalledWith(20);
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
