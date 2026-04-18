// @ts-nocheck
/**
 * Integration Test: Gallery Browsing Flow
 * Tests the complete gallery browsing workflow
 */

import { useState, useEffect, useCallback } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GalleryBrowser from '@/components/gallery/GalleryBrowser';
import * as apiClient from '@/api/client';

const mockGalleryListResponse = {
  galleries: [
    { id: 'gallery-1', timestamp: '2024-01-15T10:30:00Z', imageCount: 4 },
    { id: 'gallery-2', timestamp: '2024-01-14T15:20:00Z', imageCount: 4 },
  ],
  total: 2,
};
const mockGalleryDetailResponse = {
  galleryId: 'gallery-1',
  images: [
    { key: 'k1', model: 'gemini', url: 'https://cdn.example.com/i1.png', prompt: 'p' },
  ],
  total: 1,
};

// Mock the API client
vi.mock('@/api/client', () => ({
  listSessions: vi.fn(),
  getSessionDetail: vi.fn(),
}));

// Mock the useGallery hook to use real API calls
vi.mock('@/hooks/useGallery', () => ({
  default: function useGallery() {
    const [galleries, setGalleries] = useState([]);
    const [selectedGallery, setSelectedGallery] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchGalleries = useCallback(async () => {
      setLoading(true);
      try {
        const data = await apiClient.listSessions();
        // Map API response to expected gallery shape
        const galleriesWithPreviews = (data.galleries || []).map((g) => ({
          id: g.id,
          timestamp: g.timestamp,
          imageCount: g.imageCount,
          previewUrl: g.previewUrl,
          preview: g.previewUrl,
        }));
        setGalleries(galleriesWithPreviews);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }, []);

    useEffect(() => {
      fetchGalleries();
    }, [fetchGalleries]);

    const loadGallery = async (galleryId) => {
      setLoading(true);
      try {
        const data = await apiClient.getSessionDetail(galleryId);
        setSelectedGallery({
          id: data.galleryId,
          images: (data.images || []).map((img) => ({ model: img.model, url: img.url })),
          total: data.total,
        });
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
      fetchGalleries,
      loadGallery,
      clearSelection,
      refresh: fetchGalleries,
      autoRefresh: false,
      setAutoRefresh: () => {},
    };
  },
}));

describe('Gallery Browsing Flow - Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('completes full gallery browsing flow: list then select then view details', async () => {
    const user = userEvent.setup();
    const mockOnGallerySelect = vi.fn();

    // Mock API responses
    (apiClient.listSessions as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockGalleryListResponse,
    );
    (apiClient.getSessionDetail as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockGalleryDetailResponse,
    );

    render(<GalleryBrowser onGallerySelect={mockOnGallerySelect} />);

    // Step 1: Wait for galleries to load
    await waitFor(() => {
      expect(apiClient.listSessions).toHaveBeenCalled();
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
      expect(apiClient.getSessionDetail).toHaveBeenCalledWith('gallery-1');
    });

    // Step 5: Verify callback is called with gallery data
    await waitFor(() => {
      expect(mockOnGallerySelect).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'gallery-1',
        }),
      );
    });
  }, 10000);

  it('handles empty gallery state', async () => {
    (apiClient.listSessions as ReturnType<typeof vi.fn>).mockResolvedValue({
      galleries: [],
      total: 0,
    });

    render(<GalleryBrowser />);

    await waitFor(() => {
      expect(screen.getByText('No galleries yet')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Generate some images to start building your gallery/i),
    ).toBeInTheDocument();
  });

  it('handles gallery list error', async () => {
    (apiClient.listSessions as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Network error'),
    );

    render(<GalleryBrowser />);

    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Unable to load galleries/i)).toBeInTheDocument();
  });

  it('shows loading state during initial fetch', async () => {
    // Delay the response to see loading state
    (apiClient.listSessions as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(mockGalleryListResponse), 1000),
        ),
    );

    render(<GalleryBrowser />);

    // Loading skeletons should be visible initially
    expect(screen.getByText('Gallery')).toBeInTheDocument();

    // Wait for galleries to load
    await waitFor(
      () => {
        expect(screen.getByText('2 generations')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('allows deselecting a gallery by clicking it again', async () => {
    const user = userEvent.setup();
    const mockOnGallerySelect = vi.fn();

    (apiClient.listSessions as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockGalleryListResponse,
    );
    (apiClient.getSessionDetail as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockGalleryDetailResponse,
    );

    render(<GalleryBrowser onGallerySelect={mockOnGallerySelect} />);

    // Wait for load and select first gallery
    await waitFor(() => {
      expect(screen.getByText('2 generations')).toBeInTheDocument();
    });

    const galleryPreviews = await screen.findAllByRole('button');
    await user.click(galleryPreviews[0]);

    // Wait for selection
    await waitFor(() => {
      expect(apiClient.getSessionDetail).toHaveBeenCalled();
    });

    // Click again to deselect
    await user.click(galleryPreviews[0]);

    // Should call callback with null
    await waitFor(() => {
      expect(mockOnGallerySelect).toHaveBeenCalledWith(null);
    });
  }, 10000);
});
