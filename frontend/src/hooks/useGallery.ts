/**
 * useGallery Hook
 * Manages gallery state and data fetching
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { listGalleries, getGallery } from '@/api/client';
import { base64ToBlobUrl } from '@/utils/imageHelpers';
import type { GalleryPreview } from '@/types';

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

interface GalleryWithPreview extends GalleryPreview {
  previewData?: string;
  preview?: string;
}

interface UseGalleryReturn {
  galleries: GalleryWithPreview[];
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
  const [galleries, setGalleries] = useState<GalleryWithPreview[]>([]);
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
      const response = await listGalleries();

      // Revoke old preview blob URLs to prevent memory leaks
      previewBlobUrlsRef.current.forEach((url) => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      previewBlobUrlsRef.current = [];

      // Convert preview base64 data to blob URLs
      const galleriesWithPreviews = (
        (response.galleries || []) as GalleryWithPreview[]
      ).map((gallery) => {
        if (gallery.previewData) {
          try {
            const previewBlob = base64ToBlobUrl(gallery.previewData);
            if (previewBlob) {
              previewBlobUrlsRef.current.push(previewBlob);
              return {
                ...gallery,
                preview: previewBlob,
              };
            }
          } catch (err) {
            console.warn(`Failed to convert preview for gallery ${gallery.id}:`, err);
          }
        }
        return gallery;
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

      const response = await getGallery(galleryId);

      // Convert base64 images to blob URLs
      const imagesWithBlobs = ((response.images || []) as GalleryImage[]).map((img) => {
        if (img.output) {
          try {
            const blobUrl = base64ToBlobUrl(img.output);
            if (blobUrl) {
              imageBlobUrlsRef.current.push(blobUrl);
              return {
                ...img,
                blobUrl,
              };
            }
          } catch (err) {
            console.warn(`Failed to convert image blob for ${img.model}:`, err);
          }
        }
        return img;
      });

      setSelectedGallery({
        id: response.id,
        images: imagesWithBlobs,
        total: response.images?.length || 0,
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
