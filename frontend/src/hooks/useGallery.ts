/**
 * useGallery Hook
 * Manages gallery state and data fetching
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { listSessions, getSessionDetail } from '@/api/client';
import { base64ToBlobUrl } from '@/utils/imageHelpers';

interface GalleryItem {
  id: string;
  timestamp: string;
  imageCount: number;
  previewData?: string;
  preview?: string;
}

interface GalleryImage {
  model: string;
  url?: string;
  output?: string;
  blobUrl?: string;
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

  // Track blob URLs for cleanup to prevent memory leaks
  const previewBlobUrlsRef = useRef<string[]>([]);
  const imageBlobUrlsRef = useRef<string[]>([]);

  /**
   * Fetch list of all galleries
   */
  const fetchGalleries = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await listSessions();

      // Revoke old preview blob URLs to prevent memory leaks
      previewBlobUrlsRef.current.forEach((url) => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      previewBlobUrlsRef.current = [];

      // Map API response to GalleryItem with blob URL previews
      const galleriesWithPreviews = (response.galleries || []).map((gallery): GalleryItem => {
        const item: GalleryItem = {
          id: gallery.id,
          timestamp: gallery.timestamp,
          imageCount: gallery.imageCount,
          previewData: gallery.previewData,
        };

        if (gallery.previewData) {
          try {
            const previewBlob = base64ToBlobUrl(gallery.previewData);
            if (previewBlob) {
              previewBlobUrlsRef.current.push(previewBlob);
              return { ...item, preview: previewBlob };
            }
          } catch (err) {
            console.warn(`Failed to convert preview for gallery ${gallery.id}:`, err);
          }
        }
        return item;
      });

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
      // Revoke old image blob URLs to prevent memory leaks
      imageBlobUrlsRef.current.forEach((url) => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      imageBlobUrlsRef.current = [];

      const detail = await getSessionDetail(galleryId);

      // Convert base64 images to blob URLs
      const imagesWithBlobs: GalleryImage[] = (detail.images || []).map((img) => {
        const galleryImage: GalleryImage = {
          model: img.model,
          url: img.url,
          output: img.output,
        };

        if (img.output) {
          try {
            const blobUrl = base64ToBlobUrl(img.output);
            if (blobUrl) {
              imageBlobUrlsRef.current.push(blobUrl);
              return { ...galleryImage, blobUrl };
            }
          } catch (err) {
            console.warn(`Failed to convert image blob for ${img.model}:`, err);
          }
        }
        return galleryImage;
      });

      setSelectedGallery({
        id: detail.galleryId,
        images: imagesWithBlobs,
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

  // Cleanup: Revoke all blob URLs on unmount
  useEffect(() => {
    return () => {
      previewBlobUrlsRef.current.forEach((url) => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });

      imageBlobUrlsRef.current.forEach((url) => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
    };
  }, []);

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
