/**
 * ImageModal Component
 * Displays full-size image with keyboard navigation
 * Supports arrow keys to navigate between images
 */

import { useEffect, useState, type FC } from 'react';
import Modal from '@/components/common/Modal';
import { downloadImage } from '@/utils/imageHelpers';
import { useSound } from '@/hooks/useSound';

interface ImageData {
  image: string | null;
  model: string;
}

interface ImageModalProps {
  isOpen: boolean;
  onClose: () => void;
  images: ImageData[];
  currentIndex: number;
  onNavigate: (index: number) => void;
}

export const ImageModal: FC<ImageModalProps> = ({
  isOpen,
  onClose,
  images,
  currentIndex,
  onNavigate,
}) => {
  const { playSound } = useSound();
  const [imageError, setImageError] = useState(false);
  const [prevIndex, setPrevIndex] = useState(currentIndex);

  const currentImage = images[currentIndex];
  const hasPrevious = currentIndex > 0;
  const hasNext = currentIndex < images.length - 1;

  // Reset error when image changes (without useEffect)
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
              md:left-4
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
              md:right-4
            "
            onClick={() => handleNavigate(currentIndex + 1)}
            aria-label="Next image"
            title="Next image (Right Arrow)"
          >
            ›
          </button>
        )}

        {/* Image Container */}
        <div className="flex items-center justify-center bg-primary rounded-md min-h-[300px] max-h-[75vh] overflow-hidden">
          {imageError ? (
            <div className="flex flex-col items-center justify-center gap-2 p-8 text-text-secondary">
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
            bg-secondary rounded-b-md mt-2
            flex-col md:flex-row
          "
        >
          <div className="flex flex-col gap-1 flex-1">
            <h3 className="text-lg font-semibold text-text m-0">{currentImage.model}</h3>
            <span className="text-sm text-text-secondary">
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
                hover:bg-accent-hover hover:-translate-y-0.5
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
