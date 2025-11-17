/**
 * useGallery Hook
 * Manages gallery state and data fetching
 */

import { useState, useEffect, useCallback } from 'react';
import { listGalleries, getGallery } from '../api/client';

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

  /**
   * Fetch list of all galleries
   */
  const fetchGalleries = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await listGalleries();
      setGalleries(response.galleries || []);
      console.log(`Fetched ${response.galleries?.length || 0} galleries`);
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
      const response = await getGallery(galleryId);
      setSelectedGallery({
        id: response.galleryId,
        images: response.images || [],
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
