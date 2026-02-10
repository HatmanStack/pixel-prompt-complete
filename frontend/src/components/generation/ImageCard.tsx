/**
 * ImageCard Component
 * Individual image card with loading states
 * Memoized to prevent unnecessary re-renders in grid
 */

import { useState, useEffect, memo, type FC, type KeyboardEvent, type MouseEvent } from 'react';
import { useToast } from '@/stores/useToastStore';
import { downloadImage } from '@/utils/imageHelpers';
import { useSound } from '@/hooks/useSound';

type ImageStatus = 'pending' | 'loading' | 'completed' | 'error' | 'success';

interface ImageCardProps {
  image: string | null;
  model: string;
  status?: ImageStatus;
  error?: string | null;
  onExpand?: () => void;
}

const ImageCard: FC<ImageCardProps> = ({
  image,
  model,
  status = 'pending',
  error = null,
  onExpand,
}) => {
  const { success, error: errorToast } = useToast();
  const { playSound } = useSound();
  const [imageError, setImageError] = useState(false);

  // Reset imageError when image prop changes
  useEffect(() => {
    setImageError(false);
  }, [image]);

  const handleImageError = () => {
    setImageError(true);
  };

  const handleClick = () => {
    if ((status === 'completed' || status === 'success') && image && !imageError && onExpand) {
      playSound('expand');
      onExpand();
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((status === 'completed' || status === 'success') && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      handleClick();
    }
  };

  const handleDownload = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    if (image) {
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
      const safeModelName = model ? model.replace(/\s+/g, '-') : 'unknown';
      downloadImage(image, `pixel-prompt-${safeModelName}-${timestamp}.png`);
      playSound('click');
    }
  };

  const handleCopyUrl = async (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    if (image) {
      try {
        await navigator.clipboard.writeText(image);
        success('Image URL copied to clipboard!');
        playSound('click');
      } catch (err) {
        console.error('Failed to copy URL:', err);
        errorToast('Failed to copy URL');
      }
    }
  };

  const isCompleted = status === 'completed' || status === 'success';
  const isClickable = isCompleted && image && !imageError;

  const renderContent = () => {
    if (status === 'pending' || status === 'loading') {
      return (
        <div
          className="flex flex-col items-center justify-center gap-4 bg-primary/30 absolute inset-0"
          role="status"
          aria-busy="true"
        >
          <div
            className="w-12 h-12 border-4 border-accent/30 border-t-accent rounded-full animate-[spinBounce_1s_ease-in-out_infinite] motion-reduce:animate-none"
            aria-hidden="true"
          />
          <span className="text-sm text-text-secondary animate-[gentlePulse_2s_ease-in-out_infinite] motion-reduce:animate-none">
            {status === 'loading' ? 'Generating...' : 'Waiting...'}
          </span>
        </div>
      );
    }

    if (status === 'error' || imageError) {
      return (
        <div
          className="flex flex-col items-center justify-center gap-2 bg-error/10 p-4 absolute inset-0"
          role="alert"
          aria-live="polite"
        >
          <span className="text-3xl text-error" aria-hidden="true">
            ⚠
          </span>
          <span className="text-sm text-error text-center max-w-[90%] break-words">
            {model}: {error || 'Failed to load'}
          </span>
        </div>
      );
    }

    if (isCompleted && image) {
      return (
        <>
          <img
            src={image}
            alt={`Generated image from ${model}`}
            className="absolute inset-0 w-full h-full object-cover animate-in fade-in duration-200"
            onError={handleImageError}
            loading="lazy"
          />
          <div className="absolute top-2 right-2 flex gap-1 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
            <button
              className="
                w-8 h-8 flex items-center justify-center
                bg-black/70 text-white
                border border-white/20 rounded-md
                text-base cursor-pointer
                transition-all duration-150
                backdrop-blur-sm
                hover:bg-black/90 hover:scale-110
              "
              onClick={handleDownload}
              aria-label="Download image"
              title="Download"
            >
              ⬇
            </button>
            <button
              className="
                w-8 h-8 flex items-center justify-center
                bg-black/70 text-white
                border border-white/20 rounded-md
                text-base cursor-pointer
                transition-all duration-150
                backdrop-blur-sm
                hover:bg-black/90 hover:scale-110
              "
              onClick={handleCopyUrl}
              aria-label="Copy image URL"
              title="Copy URL"
            >
              🔗
            </button>
          </div>
        </>
      );
    }

    return null;
  };

  return (
    <div
      className={`
        group flex flex-col
        bg-secondary border border-accent/30 rounded-lg
        overflow-hidden
        shadow-md
        transition-all duration-200 ease-out
        motion-reduce:transition-none
        ${isClickable ? 'cursor-pointer hover:-translate-y-1 hover:scale-[1.02] hover:shadow-xl hover:border-accent' : ''}
        ${isClickable ? 'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 focus-visible:scale-[1.02]' : ''}
      `}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      aria-label={isClickable ? `View ${model || 'image'}` : undefined}
    >
      <div className="relative w-full pt-[100%] overflow-hidden bg-primary/30">
        {renderContent()}
      </div>

      <div className="flex items-center justify-between gap-2 py-2 px-3 bg-secondary border-t border-accent/20">
        <span
          className="text-sm text-text-secondary font-medium whitespace-nowrap overflow-hidden text-ellipsis flex-1"
          title={model}
        >
          {model}
        </span>
        {isCompleted && (
          <span className="text-sm text-success" aria-label="Generation complete">
            <span aria-hidden="true">✓</span>
            <span className="sr-only">Complete</span>
          </span>
        )}
      </div>
    </div>
  );
};

// Memoize component to prevent re-renders when props haven't changed
export default memo(ImageCard);
