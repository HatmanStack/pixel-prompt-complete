/**
 * ImageModal Component
 * Displays full-size image with metadata
 * Supports both session-based (new) and legacy array-based props
 */

import { useEffect, useState, type FC } from 'react';
import Modal from '@/components/common/Modal';
import { downloadImage } from '@/utils/imageHelpers';
import { useSound } from '@/hooks/useSound';
import type { ModelName, Iteration } from '@/types';
import { MODEL_DISPLAY_NAMES } from '@/types';

// Legacy interface for backwards compatibility
interface LegacyImageData {
  image: string | null;
  model: string;
}

interface LegacyImageModalProps {
  isOpen: boolean;
  onClose: () => void;
  images: LegacyImageData[];
  currentIndex: number;
  onNavigate: (index: number) => void;
}

// New session-based interface
interface SessionImageModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  model: ModelName;
  iteration: Iteration;
  onDownload?: () => void;
}

// Combined type to support both
type ImageModalProps = LegacyImageModalProps | SessionImageModalProps;

// Type guard to check if props are session-based
function isSessionProps(props: ImageModalProps): props is SessionImageModalProps {
  return 'iteration' in props;
}

/**
 * Format datetime for display
 */
function formatDateTime(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

export const ImageModal: FC<ImageModalProps> = (props) => {
  const { playSound } = useSound();
  const [imageError, setImageError] = useState(false);

  // Handle session-based props
  if (isSessionProps(props)) {
    const { isOpen, onClose, imageUrl, model, iteration, onDownload } = props;

    // Reset error on close/reopen
    useEffect(() => {
      if (isOpen) {
        setImageError(false);
      }
    }, [isOpen]);

    const handleDownload = () => {
      if (imageUrl) {
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
        const safeModelName = model.replace(/\s+/g, '-');
        downloadImage(imageUrl, `pixel-prompt-${safeModelName}-iter${iteration.index}-${timestamp}.png`);
        playSound('click');
        onDownload?.();
      }
    };

    const handleImageError = () => {
      setImageError(true);
    };

    return (
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        ariaLabel={`${MODEL_DISPLAY_NAMES[model]} iteration ${iteration.index}`}
      >
        <div className="flex flex-col gap-4 max-w-4xl">
          {/* Image */}
          <div className="flex items-center justify-center bg-gray-100 dark:bg-gray-900 rounded-md min-h-[300px] max-h-[70vh] overflow-hidden">
            {imageError ? (
              <div className="flex flex-col items-center justify-center gap-2 p-8 text-gray-500">
                <span className="text-3xl">⚠</span>
                <p>Failed to load image</p>
              </div>
            ) : (
              <img
                src={imageUrl}
                alt={`${MODEL_DISPLAY_NAMES[model]} iteration ${iteration.index}`}
                className="max-w-full max-h-[70vh] w-auto h-auto object-contain"
                onError={handleImageError}
              />
            )}
          </div>

          {/* Metadata */}
          <div className="flex flex-col gap-2 p-4 bg-gray-50 dark:bg-gray-800 rounded-md">
            <h3 className="font-semibold text-lg text-gray-900 dark:text-gray-100">
              {MODEL_DISPLAY_NAMES[model]} - Iteration {iteration.index}
            </h3>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {iteration.prompt}
            </p>
            {iteration.completedAt && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Generated: {formatDateTime(iteration.completedAt)}
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-2 justify-end">
            <button
              onClick={handleDownload}
              className="
                px-4 py-2 rounded
                bg-gray-200 dark:bg-gray-700
                text-gray-800 dark:text-gray-200
                hover:bg-gray-300 dark:hover:bg-gray-600
                transition-colors
              "
            >
              Download
            </button>
            <button
              onClick={onClose}
              className="
                px-4 py-2 rounded
                bg-accent text-white
                hover:bg-accent/90
                transition-colors
              "
            >
              Close
            </button>
          </div>
        </div>
      </Modal>
    );
  }

  // Handle legacy props
  const { isOpen, onClose, images, currentIndex, onNavigate } = props;
  const [prevIndex, setPrevIndex] = useState(currentIndex);

  const currentImage = images[currentIndex];
  const hasPrevious = currentIndex > 0;
  const hasNext = currentIndex < images.length - 1;

  // Reset error when image changes
  if (currentIndex !== prevIndex) {
    setImageError(false);
    setPrevIndex(currentIndex);
  }

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'ArrowLeft' && hasPrevious) {
        playSound('switch');
        onNavigate(currentIndex - 1);
      } else if (e.key === 'ArrowRight' && hasNext) {
        playSound('switch');
        onNavigate(currentIndex + 1);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, currentIndex, hasPrevious, hasNext, onNavigate, playSound]);

  const handleDownload = () => {
    if (currentImage?.image) {
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
      const safeModelName = currentImage.model
        ? currentImage.model.replace(/\s+/g, '-')
        : 'unknown';
      downloadImage(currentImage.image, `pixel-prompt-${safeModelName}-${timestamp}.png`);
      playSound('click');
    }
  };

  const handleImageError = () => {
    setImageError(true);
  };

  const handleNavigate = (index: number) => {
    playSound('switch');
    onNavigate(index);
  };

  if (!currentImage) {
    return null;
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      ariaLabel={`Expanded view of ${currentImage.model} image`}
    >
      <div className="relative flex flex-col min-w-[300px] max-w-[90vw]">
        {/* Navigation Buttons */}
        {hasPrevious && (
          <button
            className="
              absolute top-1/2 left-4 -translate-y-1/2 z-10
              w-12 h-12
              flex items-center justify-center
              bg-black/50 border-none rounded-full
              text-white text-3xl cursor-pointer
              transition-all duration-200
              hover:bg-black/70 hover:scale-110
              focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
            "
            onClick={() => handleNavigate(currentIndex - 1)}
            aria-label="Previous image"
            title="Previous image (Left Arrow)"
          >
            ‹
          </button>
        )}

        {hasNext && (
          <button
            className="
              absolute top-1/2 right-4 -translate-y-1/2 z-10
              w-12 h-12
              flex items-center justify-center
              bg-black/50 border-none rounded-full
              text-white text-3xl cursor-pointer
              transition-all duration-200
              hover:bg-black/70 hover:scale-110
              focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
            "
            onClick={() => handleNavigate(currentIndex + 1)}
            aria-label="Next image"
            title="Next image (Right Arrow)"
          >
            ›
          </button>
        )}

        {/* Image Container */}
        <div className="flex items-center justify-center bg-gray-100 dark:bg-gray-900 rounded-md min-h-[300px] max-h-[75vh] overflow-hidden">
          {imageError ? (
            <div className="flex flex-col items-center justify-center gap-2 p-8 text-gray-500">
              <span className="text-3xl">⚠</span>
              <p>Failed to load image</p>
            </div>
          ) : (
            <img
              src={currentImage.image || ''}
              alt={`Full-size image from ${currentImage.model}`}
              className="max-w-full max-h-[75vh] w-auto h-auto object-contain rounded-md"
              onError={handleImageError}
            />
          )}
        </div>

        {/* Image Info */}
        <div
          className="
            flex justify-between items-center gap-4 p-4
            bg-gray-100 dark:bg-gray-800 rounded-b-md mt-2
            flex-col md:flex-row
          "
        >
          <div className="flex flex-col gap-1 flex-1">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 m-0">
              {currentImage.model}
            </h3>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {currentIndex + 1} / {images.length}
            </span>
          </div>
          <div className="flex gap-2 w-full md:w-auto">
            <button
              className="
                flex-1 md:flex-initial
                flex items-center justify-center gap-1
                py-2 px-4
                bg-accent border-none rounded-md
                text-white text-sm font-medium
                cursor-pointer
                transition-all duration-200
                hover:bg-accent/90
                focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
              "
              onClick={handleDownload}
              aria-label="Download image"
              title="Download"
            >
              ⬇ Download
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default ImageModal;
