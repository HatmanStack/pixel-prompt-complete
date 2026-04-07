/**
 * useGallery Hook
 * Manages gallery state and data fetching
 */

import { useState, useEffect, useCallback } from 'react';
import { listSessions, getSessionDetail } from '@/api/client';

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

  /**
   * Fetch list of all galleries
   */
  const fetchGalleries = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await listSessions();

      // Map API response to GalleryItem using CloudFront preview URLs
      const galleriesWithPreviews = (response.galleries || []).map(
        (gallery): GalleryItem => ({
          id: gallery.id,
          timestamp: gallery.timestamp,
          imageCount: gallery.imageCount,
          previewUrl: gallery.previewUrl,
          preview: gallery.previewUrl,
        }),
      );

      setGalleries(galleriesWithPreviews);
    } catch (err) {
      console.error('Error fetching galleries:', err);
      setError(err instanceof Error ? err.message : 'Failed to load galleries');
      setGalleries([]);
    } finally {
      setLoading(false);
    }
  }, []);

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
  };
}

export default useGallery;
