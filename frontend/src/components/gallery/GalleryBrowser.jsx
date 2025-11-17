/**
 * GalleryBrowser Component
 * Browse and select past image generation galleries
 * Optimized with useCallback for GalleryPreview memoization
 */

import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import useGallery from '../../hooks/useGallery';
import GalleryPreview from './GalleryPreview';
import LoadingSkeleton from '../common/LoadingSkeleton';
import styles from './GalleryBrowser.module.css';

function GalleryBrowser({ onGallerySelect }) {
  const {
    galleries,
    selectedGallery,
    loading,
    error,
    loadGallery,
    clearSelection,
  } = useGallery();

  const [selectedId, setSelectedId] = useState(null);

  // Memoize gallery selection handler to prevent breaking GalleryPreview memoization
  const handleSelect = useCallback(async (gallery) => {
    if (selectedId === gallery.id) {
      // Deselect if clicking the same gallery
      setSelectedId(null);
      clearSelection();
      if (onGallerySelect) {
        onGallerySelect(null);
      }
    } else {
      // Select new gallery
      setSelectedId(gallery.id);
      await loadGallery(gallery.id);
    }
  }, [selectedId, clearSelection, loadGallery, onGallerySelect]);

  // Notify parent when gallery is loaded
  useEffect(() => {
    if (selectedGallery && onGallerySelect) {
      onGallerySelect(selectedGallery);
    }
  }, [selectedGallery, onGallerySelect]);

  // Loading state
  if (loading && galleries.length === 0) {
    return (
      <div className={styles.browser}>
        <div className={styles.header}>
          <h3 className={styles.title}>Gallery</h3>
        </div>
        <div className={styles.grid}>
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
      <div className={styles.browser}>
        <div className={styles.header}>
          <h3 className={styles.title}>Gallery</h3>
        </div>
        <div className={styles.empty}>
          <p className={styles.errorMessage}>⚠ {error}</p>
          <p className={styles.helpText}>Unable to load galleries. Please try again later.</p>
        </div>
      </div>
    );
  }

  // Empty state
  if (galleries.length === 0) {
    return (
      <div className={styles.browser}>
        <div className={styles.header}>
          <h3 className={styles.title}>Gallery</h3>
        </div>
        <div className={styles.empty}>
          <p className={styles.emptyIcon}>🖼</p>
          <p className={styles.emptyMessage}>No galleries yet</p>
          <p className={styles.helpText}>
            Generate some images to start building your gallery
          </p>
        </div>
      </div>
    );
  }

  // Galleries loaded
  return (
    <div className={styles.browser}>
      <div className={styles.header}>
        <h3 className={styles.title}>Gallery</h3>
        <p className={styles.subtitle}>{galleries.length} {galleries.length === 1 ? 'generation' : 'generations'}</p>
      </div>

      <div className={styles.scrollContainer}>
        <div className={styles.grid}>
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
        <div className={styles.loadingOverlay}>
          <div className={styles.loadingSpinner} />
          <p>Loading gallery...</p>
        </div>
      )}
    </div>
  );
}

GalleryBrowser.propTypes = {
  onGallerySelect: PropTypes.func,
};

GalleryBrowser.defaultProps = {
  onGallerySelect: null,
};

export default GalleryBrowser;
