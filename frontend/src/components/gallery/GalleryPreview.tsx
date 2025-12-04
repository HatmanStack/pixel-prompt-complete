/**
 * GalleryPreview Component
 * Preview card for a single gallery
 * Memoized to prevent re-renders when other gallery items update
 */

import { memo, type FC, type KeyboardEvent, type SyntheticEvent } from 'react';
import { useSound } from '@/hooks/useSound';

interface GalleryData {
  id: string;
  timestamp: string;
  preview?: string;
  imageCount?: number;
}

interface GalleryPreviewProps {
  gallery: GalleryData;
  isSelected?: boolean;
  onClick: () => void;
}

const GalleryPreview: FC<GalleryPreviewProps> = ({ gallery, isSelected = false, onClick }) => {
  const { playSound } = useSound();

  // Format timestamp for display
  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return timestamp;
    }
  };

  // Handle preview image loading
  const handleImageError = (e: SyntheticEvent<HTMLImageElement>) => {
    e.currentTarget.src = '/vite.svg';
    e.currentTarget.alt = 'Preview unavailable';
  };

  const handleClick = () => {
    playSound('switch');
    onClick();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  };

  const imageCount = gallery.imageCount || 0;

  return (
    <div
      className={`
        flex flex-col
        bg-secondary border-2 rounded-lg
        overflow-hidden cursor-pointer
        transition-all duration-200
        motion-reduce:transition-none
        min-w-[150px] max-w-[200px]
        md:min-w-[120px] md:max-w-[150px]
        hover:-translate-y-1 hover:scale-[1.02] hover:shadow-lg hover:border-accent
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-primary
        ${isSelected ? 'border-accent shadow-[0_0_0_3px_rgba(181,131,146,0.3)]' : 'border-accent/30'}
      `}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      aria-label={`Gallery from ${formatTimestamp(gallery.timestamp)}`}
    >
      <div className="relative w-full h-[150px] md:h-[120px] overflow-hidden bg-primary">
        {gallery.preview ? (
          <img
            src={gallery.preview}
            alt={`Preview from ${formatTimestamp(gallery.timestamp)}`}
            className="w-full h-full object-cover"
            onError={handleImageError}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-primary text-text-secondary text-sm">
            <span className="text-5xl opacity-60">🖼️</span>
            <span>
              {imageCount} {imageCount === 1 ? 'image' : 'images'}
            </span>
          </div>
        )}
      </div>
      <div className="p-2 bg-secondary flex flex-col gap-1">
        <p className="m-0 text-sm text-text font-medium whitespace-nowrap overflow-hidden text-ellipsis">
          {formatTimestamp(gallery.timestamp)}
        </p>
        <p className="m-0 text-xs text-text-secondary">
          {imageCount} {imageCount === 1 ? 'image' : 'images'}
        </p>
      </div>
    </div>
  );
};

// Memoize component to prevent re-renders when other gallery items update
export default memo(GalleryPreview);
