/**
 * GalleryBrowser Component
 * Browse and select past image generation galleries
 * Optimized with useCallback for GalleryPreview memoization
 */

import { useState, useEffect, useCallback, type FC } from 'react';
import useGallery from '@/hooks/useGallery';
import GalleryPreview from './GalleryPreview';
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton';
import { useSound } from '@/hooks/useSound';

interface GalleryImage {
  model: string;
  url?: string;
  blobUrl?: string;
  timestamp?: string;
}

interface SelectedGalleryData {
  id: string;
  images: GalleryImage[];
  total: number;
}

interface GalleryBrowserProps {
  onGallerySelect?: (gallery: SelectedGalleryData | null) => void;
}

export const GalleryBrowser: FC<GalleryBrowserProps> = ({ onGallerySelect }) => {
  const { playSound } = useSound();
  const { galleries, selectedGallery, loading, error, loadGallery, clearSelection } = useGallery();

  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Memoize gallery selection handler
  const handleSelect = useCallback(
    async (gallery: { id: string }) => {
      if (selectedId === gallery.id) {
        // Deselect if clicking the same gallery
        setSelectedId(null);
        clearSelection();
        if (onGallerySelect) {
          onGallerySelect(null);
        }
      } else {
        // Select new gallery
        playSound('switch');
        setSelectedId(gallery.id);
        await loadGallery(gallery.id);
      }
    },
    [selectedId, clearSelection, loadGallery, onGallerySelect, playSound],
  );

  // Notify parent when gallery is loaded
  useEffect(() => {
    if (selectedGallery && onGallerySelect) {
      onGallerySelect(selectedGallery);
    }
  }, [selectedGallery, onGallerySelect]);

  // Loading state
  if (loading && galleries.length === 0) {
    return (
      <div className="w-full bg-secondary rounded-lg p-4 mb-6 shadow-md">
        <div className="flex justify-between items-baseline mb-4 pb-2 border-b border-accent/20">
          <h3 className="m-0 text-lg font-semibold text-text">Gallery</h3>
        </div>
        <div className="flex gap-4">
          {[...Array(4)].map((_, i) => (
            <LoadingSkeleton key={i} height={150} />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error && galleries.length === 0) {
    return (
      <div className="w-full bg-secondary rounded-lg p-4 mb-6 shadow-md">
        <div className="flex justify-between items-baseline mb-4 pb-2 border-b border-accent/20">
          <h3 className="m-0 text-lg font-semibold text-text">Gallery</h3>
        </div>
        <div className="text-center py-8 px-4">
          <p className="m-0 mb-2 text-lg font-semibold text-error">⚠ {error}</p>
          <p className="m-0 text-sm text-text-secondary">
            Unable to load galleries. Please try again later.
          </p>
        </div>
      </div>
    );
  }

  // Empty state
  if (galleries.length === 0) {
    return (
      <div className="w-full bg-secondary rounded-lg p-4 mb-6 shadow-md">
        <div className="flex justify-between items-baseline mb-4 pb-2 border-b border-accent/20">
          <h3 className="m-0 text-lg font-semibold text-text">Gallery</h3>
        </div>
        <div className="text-center py-8 px-4">
          <p className="text-6xl m-0 mb-4 opacity-50">🖼</p>
          <p className="m-0 mb-2 text-lg font-semibold text-text">No galleries yet</p>
          <p className="m-0 text-sm text-text-secondary">
            Generate some images to start building your gallery
          </p>
        </div>
      </div>
    );
  }

  // Galleries loaded
  return (
    <div className="w-full bg-secondary rounded-lg p-4 mb-6 shadow-md">
      <div className="flex justify-between items-baseline mb-4 pb-2 border-b border-accent/20 flex-col md:flex-row gap-1">
        <h3 className="m-0 text-lg font-semibold text-text">Gallery</h3>
        <p className="m-0 text-sm text-text-secondary">
          {galleries.length} {galleries.length === 1 ? 'generation' : 'generations'}
        </p>
      </div>

      <div
        className="
          overflow-x-auto overflow-y-hidden
          scrollbar-thin scrollbar-thumb-accent/30 scrollbar-track-transparent
        "
      >
        <div className="flex gap-4 py-1 min-w-min">
          {galleries.map((gallery) => (
            <GalleryPreview
              key={gallery.id}
              gallery={gallery}
              isSelected={selectedId === gallery.id}
              onClick={() => handleSelect(gallery)}
            />
          ))}
        </div>
      </div>

      {loading && selectedId && (
        <div className="fixed inset-0 bg-black/60 flex flex-col items-center justify-center z-[1000] text-white">
          <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin mb-4" />
          <p>Loading gallery...</p>
        </div>
      )}
    </div>
  );
};

export default GalleryBrowser;
