/**
 * useGallery Hook
 * Manages gallery state and data fetching
 */

import { useState, useEffect, useCallback } from 'react';
import { listSessions, getSessionDetail } from '@/api/client';
import type { SessionGalleryListResponse } from '@/types/api';

/**
 * How many galleries the browser asks for. The backend clamps to 1..50 and
 * defaults to 20 on its own, so this is a preference, not the bound.
 */
const GALLERY_PAGE_SIZE = 20;

interface GalleryItem {
  id: string;
  timestamp: string;
  imageCount: number;
  previewUrl?: string;
  preview?: string;
}

interface GalleryImage {
  model: string;
  url?: string;
}

interface SelectedGallery {
  id: string;
  images: GalleryImage[];
  total: number;
}

interface UseGalleryReturn {
  galleries: GalleryItem[];
  selectedGallery: SelectedGallery | null;
  loading: boolean;
  error: string | null;
  fetchGalleries: () => Promise<void>;
  loadGallery: (galleryId: string) => Promise<void>;
  clearSelection: () => void;
  refresh: () => void;
  autoRefresh: boolean;
  setAutoRefresh: (value: boolean) => void;
  /** True while a loadMore is in flight, so the control can disable itself. */
  loadingMore: boolean;
  /** True when the last response carried a cursor, i.e. more pages exist. */
  hasMore: boolean;
  loadMore: () => Promise<void>;
}

/**
 * Custom hook for gallery management
 */
function useGallery(): UseGalleryReturn {
  const [galleries, setGalleries] = useState<GalleryItem[]>([]);
  const [selectedGallery, setSelectedGallery] = useState<SelectedGallery | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const toItems = (response: SessionGalleryListResponse): GalleryItem[] =>
    (response.galleries || []).map((gallery): GalleryItem => ({
      id: gallery.id,
      timestamp: gallery.timestamp,
      imageCount: gallery.imageCount,
      previewUrl: gallery.previewUrl,
      preview: gallery.previewUrl,
    }));

  /**
   * Fetch the first page of galleries, replacing whatever is loaded.
   */
  const fetchGalleries = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await listSessions(GALLERY_PAGE_SIZE);

      setGalleries(toItems(response));
      // The endpoint is paginated: it returns at most `limit` folders and a
      // cursor when more exist. Dropping that cursor made every gallery past
      // the first page unreachable from the app.
      setNextCursor(response.nextCursor ?? null);
    } catch (err) {
      console.error('Error fetching galleries:', err);
      setError(err instanceof Error ? err.message : 'Failed to load galleries');
      setGalleries([]);
      setNextCursor(null);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Append the next page. No-op when no cursor is held or one is in flight.
   */
  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore) return;

    setLoadingMore(true);
    setError(null);

    try {
      const response = await listSessions(GALLERY_PAGE_SIZE, nextCursor);

      // De-duplicate by id. The backend anchors its cursor to the folders it
      // asked for rather than the ones that survived expansion, so overlap
      // should not occur -- but a gallery rendered twice is a visible bug and
      // guarding costs one Set.
      setGalleries((prev) => {
        const seen = new Set(prev.map((g) => g.id));
        return [...prev, ...toItems(response).filter((g) => !seen.has(g.id))];
      });
      setNextCursor(response.nextCursor ?? null);
    } catch (err) {
      console.error('Error loading more galleries:', err);
      setError(err instanceof Error ? err.message : 'Failed to load more galleries');
      // Cursor deliberately retained: the page that failed is still the next
      // one to fetch, so the control stays live and the user can retry.
    } finally {
      setLoadingMore(false);
    }
  }, [nextCursor, loadingMore]);

  /**
   * Load a specific gallery's images
   */
  const loadGallery = useCallback(async (galleryId: string) => {
    if (!galleryId) {
      console.warn('loadGallery called with no galleryId');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const detail = await getSessionDetail(galleryId);

      const images: GalleryImage[] = (detail.images || []).map((img) => ({
        model: img.model,
        url: img.url,
      }));

      setSelectedGallery({
        id: detail.galleryId,
        images,
        total: detail.total,
      });
    } catch (err) {
      console.error(`Error loading gallery ${galleryId}:`, err);
      setError(err instanceof Error ? err.message : 'Failed to load gallery');
      setSelectedGallery(null);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Clear selected gallery
   */
  const clearSelection = useCallback(() => {
    setSelectedGallery(null);
  }, []);

  /**
   * Refresh gallery list
   */
  const refresh = useCallback(() => {
    fetchGalleries();
  }, [fetchGalleries]);

  // Auto-fetch galleries on mount
  useEffect(() => {
    fetchGalleries();
  }, [fetchGalleries]);

  // Auto-refresh galleries if enabled
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchGalleries();
    }, 10000);

    return () => clearInterval(interval);
  }, [autoRefresh, fetchGalleries]);

  return {
    galleries,
    selectedGallery,
    loading,
    error,
    fetchGalleries,
    loadGallery,
    clearSelection,
    refresh,
    autoRefresh,
    setAutoRefresh,
    loadingMore,
    hasMore: nextCursor !== null,
    loadMore,
  };
}

export default useGallery;
