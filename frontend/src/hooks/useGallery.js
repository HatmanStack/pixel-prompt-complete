/**
 * useGallery Hook
 * Manages gallery state and data fetching
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { listGalleries, getGallery } from '../api/client';
import { base64ToBlobUrl } from '../utils/imageHelpers';

/**
 * Custom hook for gallery management
 * @returns {Object} Gallery state and functions
 */
function useGallery() {
  const [galleries, setGalleries] = useState([]);
  const [selectedGallery, setSelectedGallery] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Track blob URLs for cleanup to prevent memory leaks
  const previewBlobUrlsRef = useRef([]);
  const imageBlobUrlsRef = useRef([]);

  /**
   * Fetch list of all galleries
   */
  const fetchGalleries = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await listGalleries();

      // Revoke old preview blob URLs to prevent memory leaks
      previewBlobUrlsRef.current.forEach(url => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      previewBlobUrlsRef.current = [];

      // Convert preview base64 data to blob URLs
      const galleriesWithPreviews = (response.galleries || []).map(gallery => {
        if (gallery.previewData) {
          try {
            const previewBlob = base64ToBlobUrl(gallery.previewData);
            if (previewBlob) {
              previewBlobUrlsRef.current.push(previewBlob);
              return {
                ...gallery,
                preview: previewBlob,  // Replace URL with blob URL
              };
            }
          } catch (err) {
            console.warn(`Failed to convert preview for gallery ${gallery.id}:`, err);
          }
        }
        return gallery;
      });

      setGalleries(galleriesWithPreviews);
      console.log(`Fetched ${galleriesWithPreviews.length} galleries`);
    } catch (err) {
      console.error('Error fetching galleries:', err);
      setError(err.message || 'Failed to load galleries');
      setGalleries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Load a specific gallery's images
   * @param {string} galleryId - The gallery ID to load
   */
  const loadGallery = useCallback(async (galleryId) => {
    if (!galleryId) {
      console.warn('loadGallery called with no galleryId');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Revoke old image blob URLs to prevent memory leaks
      imageBlobUrlsRef.current.forEach(url => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      imageBlobUrlsRef.current = [];

      const response = await getGallery(galleryId);

      // Convert base64 images to blob URLs
      const imagesWithBlobs = (response.images || []).map(img => {
        if (img.output) {
          try {
            // Convert base64 to blob URL
            const blobUrl = base64ToBlobUrl(img.output);
            if (blobUrl) {
              imageBlobUrlsRef.current.push(blobUrl);
              return {
                ...img,
                blobUrl,  // Add blob URL for display
              };
            }
          } catch (err) {
            console.warn(`Failed to convert image blob for ${img.model}:`, err);
          }
        }
        return img;
      });

      setSelectedGallery({
        id: response.galleryId,
        images: imagesWithBlobs,
        total: response.total || 0,
      });
      console.log(`Loaded gallery ${galleryId} with ${response.images?.length || 0} images`);
    } catch (err) {
      console.error(`Error loading gallery ${galleryId}:`, err);
      setError(err.message || 'Failed to load gallery');
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
   * Refresh gallery list (for auto-refresh after generation)
   */
  const refresh = useCallback(() => {
    fetchGalleries();
  }, [fetchGalleries]);

  // Auto-fetch galleries on mount
  useEffect(() => {
    fetchGalleries();
  }, [fetchGalleries]);

  // Auto-refresh galleries if enabled (useful during image generation)
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchGalleries();
    }, 10000); // Refresh every 10 seconds

    return () => clearInterval(interval);
  }, [autoRefresh, fetchGalleries]);

  // Cleanup: Revoke all blob URLs on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      // Revoke preview blob URLs
      previewBlobUrlsRef.current.forEach(url => {
        if (url && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });

      // Revoke image blob URLs
      imageBlobUrlsRef.current.forEach(url => {
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
