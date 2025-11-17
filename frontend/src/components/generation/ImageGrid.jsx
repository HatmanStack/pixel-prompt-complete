/**
 * ImageGrid Component
 * Grid layout for displaying 9 generated images
 * Optimized with useCallback to prevent breaking ImageCard memoization
 * Includes ImageModal for full-screen viewing with keyboard navigation
 * Includes batch download for all completed images
 * Supports Ctrl+Shift+D keyboard shortcut for download all
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { useToast } from '../../context/ToastContext';
import { downloadImage } from '../../utils/imageHelpers';
import ImageCard from './ImageCard';
import ImageModal from '../features/generation/ImageModal';
import styles from './ImageGrid.module.css';

function ImageGrid({ images, modelNames = [] }) {
  const { success, error: errorToast, info } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);

  // Memoize image slots to prevent recreation on every render
  const imageSlots = useMemo(() => {
    return Array(9).fill(null).map((_, index) => {
      const imageData = images[index];
      const modelName = modelNames[index] || `Model ${index + 1}`;

      return {
        image: imageData?.imageUrl || imageData?.image || null,
        model: imageData?.model || modelName,
        status: imageData?.status || 'pending',
        error: imageData?.error || null,
      };
    });
  }, [images, modelNames]);

  // Get only completed images for modal navigation
  const completedImages = useMemo(() => {
    return imageSlots
      .map((slot, index) => ({ ...slot, originalIndex: index }))
      .filter(slot => slot.status === 'completed' && slot.image);
  }, [imageSlots]);

  // Memoize handleExpand to prevent breaking ImageCard memoization
  const handleExpand = useCallback((index) => {
    // Find the index in completedImages array
    const completedIndex = completedImages.findIndex(img => img.originalIndex === index);
    if (completedIndex !== -1) {
      setCurrentImageIndex(completedIndex);
      setModalOpen(true);
    }
  }, [completedImages]);

  // Memoize handleCloseModal callback
  const handleCloseModal = useCallback(() => {
    setModalOpen(false);
  }, []);

  // Memoize handleNavigate callback for modal navigation
  const handleNavigate = useCallback((newIndex) => {
    setCurrentImageIndex(newIndex);
  }, []);

  // Handle batch download of all completed images
  const handleDownloadAll = useCallback(async () => {
    if (isDownloading || completedImages.length === 0) return;

    setIsDownloading(true);
    info(`Downloading ${completedImages.length} images...`);

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < completedImages.length; i++) {
      const img = completedImages[i];
      try {
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
        const safeModelName = img.model ? img.model.replace(/\s+/g, '-') : 'unknown';
        await downloadImage(img.image, `pixel-prompt-${safeModelName}-${timestamp}.png`);
        successCount++;
        // Small delay to avoid overwhelming the browser
        await new Promise(resolve => setTimeout(resolve, 100));
      } catch (err) {
        console.error(`Failed to download image from ${img.model}:`, err);
        failCount++;
      }
    }

    setIsDownloading(false);

    if (failCount === 0) {
      success(`Successfully downloaded ${successCount} images!`);
    } else if (successCount > 0) {
      info(`Downloaded ${successCount} images (${failCount} failed)`);
    } else {
      errorToast(`Failed to download images`);
    }
  }, [completedImages, isDownloading, success, errorToast, info]);

  // Listen for keyboard shortcut (Ctrl+Shift+D)
  useEffect(() => {
    const handleDownloadAllTrigger = () => {
      handleDownloadAll();
    };

    document.addEventListener('download-all-trigger', handleDownloadAllTrigger);
    return () => {
      document.removeEventListener('download-all-trigger', handleDownloadAllTrigger);
    };
  }, [handleDownloadAll]);

  return (
    <>
      {/* Download All Button */}
      {completedImages.length > 0 && (
        <div className={styles.downloadAllContainer}>
          <button
            className={styles.downloadAllButton}
            onClick={handleDownloadAll}
            disabled={isDownloading}
            aria-label={`Download all ${completedImages.length} images`}
          >
            {isDownloading ? '⏳ Downloading...' : `⬇ Download All (${completedImages.length})`}
          </button>
        </div>
      )}

      <div className={styles.grid}>
        {imageSlots.map((slot, index) => (
          <ImageCard
            key={index}
            image={slot.image}
            model={slot.model}
            status={slot.status}
            error={slot.error}
            onExpand={() => handleExpand(index)}
          />
        ))}
      </div>

      {/* Image Modal with keyboard navigation */}
      <ImageModal
        isOpen={modalOpen}
        onClose={handleCloseModal}
        images={completedImages}
        currentIndex={currentImageIndex}
        onNavigate={handleNavigate}
      />
    </>
  );
}

export default ImageGrid;
