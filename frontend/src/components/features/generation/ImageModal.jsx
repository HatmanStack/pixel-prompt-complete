/**
 * ImageModal Component
 * Displays full-size image with keyboard navigation
 * Supports arrow keys to navigate between images
 */

import { useEffect, useState } from 'react';
import Modal from '../../common/Modal';
import { downloadImage } from '../../../utils/imageHelpers';
import styles from './ImageModal.module.css';

function ImageModal({ isOpen, onClose, images, currentIndex, onNavigate }) {
  const [imageError, setImageError] = useState(false);

  const currentImage = images[currentIndex];
  const hasPrevious = currentIndex > 0;
  const hasNext = currentIndex < images.length - 1;

  // Reset error when image changes
  useEffect(() => {
    setImageError(false);
  }, [currentIndex]);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;

      if (e.key === 'ArrowLeft' && hasPrevious) {
        onNavigate(currentIndex - 1);
      } else if (e.key === 'ArrowRight' && hasNext) {
        onNavigate(currentIndex + 1);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, currentIndex, hasPrevious, hasNext, onNavigate]);

  const handleDownload = () => {
    if (currentImage?.image) {
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
      const safeModelName = currentImage.model ? currentImage.model.replace(/\s+/g, '-') : 'unknown';
      downloadImage(currentImage.image, `pixel-prompt-${safeModelName}-${timestamp}.png`);
    }
  };

  const handleImageError = () => {
    setImageError(true);
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
      <div className={styles.imageModal}>
        {/* Navigation Buttons */}
        {hasPrevious && (
          <button
            className={`${styles.navButton} ${styles.navLeft}`}
            onClick={() => onNavigate(currentIndex - 1)}
            aria-label="Previous image"
            title="Previous image (Left Arrow)"
          >
            ‹
          </button>
        )}

        {hasNext && (
          <button
            className={`${styles.navButton} ${styles.navRight}`}
            onClick={() => onNavigate(currentIndex + 1)}
            aria-label="Next image"
            title="Next image (Right Arrow)"
          >
            ›
          </button>
        )}

        {/* Image Container */}
        <div className={styles.imageContainer}>
          {imageError ? (
            <div className={styles.error}>
              <span className={styles.errorIcon}>⚠</span>
              <p>Failed to load image</p>
            </div>
          ) : (
            <img
              src={currentImage.image}
              alt={`Full-size image from ${currentImage.model}`}
              className={styles.image}
              onError={handleImageError}
            />
          )}
        </div>

        {/* Image Info */}
        <div className={styles.footer}>
          <div className={styles.info}>
            <h3 className={styles.modelName}>{currentImage.model}</h3>
            <span className={styles.imageCounter}>
              {currentIndex + 1} / {images.length}
            </span>
          </div>
          <div className={styles.actions}>
            <button
              className={styles.actionButton}
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
}

export default ImageModal;
