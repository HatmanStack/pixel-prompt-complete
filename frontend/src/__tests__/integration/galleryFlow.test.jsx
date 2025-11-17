/**
 * Integration Test: Gallery Browsing Flow
 * Tests the complete gallery browsing workflow
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GalleryBrowser from '../../components/gallery/GalleryBrowser';
import * as apiClient from '../../api/client';
import { mockGalleryListResponse, mockGalleryDetailResponse } from '../fixtures/apiResponses';

// Mock the API client
vi.mock('../../api/client');

// Mock the useGallery hook to use real API calls
vi.mock('../../hooks/useGallery', () => ({
  default: () => {
    const [galleries, setGalleries] = useState([]);
    const [selectedGallery, setSelectedGallery] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
      const fetchGalleries = async () => {
        setLoading(true);
        try {
          const data = await apiClient.listGalleries();
          setGalleries(data.galleries);
        } catch (err) {
          setError(err.message);
        } finally {
          setLoading(false);
        }
      };
      fetchGalleries();
    }, []);

    const loadGallery = async (galleryId) => {
      setLoading(true);
      try {
        const data = await apiClient.getGallery(galleryId);
        setSelectedGallery(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    const clearSelection = () => {
      setSelectedGallery(null);
    };

    return {
      galleries,
      selectedGallery,
      loading,
      error,
      loadGallery,
      clearSelection
    };
  }
}));

import { useState, useEffect } from 'react';

describe('Gallery Browsing Flow - Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('completes full gallery browsing flow: list → select → view details', async () => {
    const user = userEvent.setup();
    const mockOnGallerySelect = vi.fn();

    // Mock API responses
    apiClient.listGalleries.mockResolvedValue(mockGalleryListResponse);
    apiClient.getGallery.mockResolvedValue(mockGalleryDetailResponse);

    render(<GalleryBrowser onGallerySelect={mockOnGallerySelect} />);

    // Step 1: Wait for galleries to load
    await waitFor(() => {
      expect(apiClient.listGalleries).toHaveBeenCalled();
    });

    // Step 2: Verify gallery list is displayed
    await waitFor(() => {
      expect(screen.getByText('2 generations')).toBeInTheDocument();
    });

    // Step 3: User clicks on a gallery preview
    const galleryPreviews = await screen.findAllByRole('button');
    expect(galleryPreviews.length).toBeGreaterThan(0);

    await user.click(galleryPreviews[0]);

    // Step 4: Verify gallery detail is fetched
    await waitFor(() => {
      expect(apiClient.getGallery).toHaveBeenCalledWith('2025-11-16-10-30-00');
    });

    // Step 5: Verify callback is called with gallery data
    await waitFor(() => {
      expect(mockOnGallerySelect).toHaveBeenCalledWith(
        expect.objectContaining({
          galleryId: '2025-11-16-10-30-00'
        })
      );
    });
  }, 10000);

  it('handles empty gallery state', async () => {
    apiClient.listGalleries.mockResolvedValue({ galleries: [], total: 0 });

    render(<GalleryBrowser />);

    await waitFor(() => {
      expect(screen.getByText('No galleries yet')).toBeInTheDocument();
    });

    expect(screen.getByText(/Generate some images to start building your gallery/i)).toBeInTheDocument();
  });

  it('handles gallery list error', async () => {
    apiClient.listGalleries.mockRejectedValue(new Error('Network error'));

    render(<GalleryBrowser />);

    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Unable to load galleries/i)).toBeInTheDocument();
  });

  it('shows loading state during initial fetch', async () => {
    // Delay the response to see loading state
    apiClient.listGalleries.mockImplementation(() =>
      new Promise(resolve => setTimeout(() => resolve(mockGalleryListResponse), 1000))
    );

    render(<GalleryBrowser />);

    // Loading skeletons should be visible initially
    expect(screen.getByText('Gallery')).toBeInTheDocument();

    // Wait for galleries to load
    await waitFor(() => {
      expect(screen.getByText('2 generations')).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('allows deselecting a gallery by clicking it again', async () => {
    const user = userEvent.setup();
    const mockOnGallerySelect = vi.fn();

    apiClient.listGalleries.mockResolvedValue(mockGalleryListResponse);
    apiClient.getGallery.mockResolvedValue(mockGalleryDetailResponse);

    render(<GalleryBrowser onGallerySelect={mockOnGallerySelect} />);

    // Wait for load and select first gallery
    await waitFor(() => {
      expect(screen.getByText('2 generations')).toBeInTheDocument();
    });

    const galleryPreviews = await screen.findAllByRole('button');
    await user.click(galleryPreviews[0]);

    // Wait for selection
    await waitFor(() => {
      expect(apiClient.getGallery).toHaveBeenCalled();
    });

    // Click again to deselect
    await user.click(galleryPreviews[0]);

    // Should call callback with null
    await waitFor(() => {
      expect(mockOnGallerySelect).toHaveBeenCalledWith(null);
    });
  }, 10000);
});
