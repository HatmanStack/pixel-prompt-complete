/**
 * GalleryPreview Component
 * Preview card for a single gallery
 * Memoized to prevent re-renders when other gallery items update
 */

import { memo } from 'react';
import PropTypes from 'prop-types';
import styles from './GalleryPreview.module.css';

function GalleryPreview({ gallery, isSelected, onClick }) {
  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (err) {
      return timestamp;
    }
  };

  // Handle preview image loading
  const handleImageError = (e) => {
    e.target.src = '/vite.svg'; // Fallback to Vite logo
    e.target.alt = 'Preview unavailable';
  };

  return (
    <div
      className={`${styles.preview} ${isSelected ? styles.selected : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      aria-label={`Gallery from ${formatTimestamp(gallery.timestamp)}`}
    >
      <div className={styles.imageContainer}>
        {gallery.preview ? (
          <img
            src={gallery.preview}
            alt={`Gallery preview from ${formatTimestamp(gallery.timestamp)}`}
            className={styles.image}
            onError={handleImageError}
          />
        ) : (
          <div className={styles.placeholder}>
            <span>No preview</span>
          </div>
        )}
        <div className={styles.overlay}>
          <span className={styles.imageCount}>{gallery.imageCount || 0} images</span>
        </div>
      </div>
      <div className={styles.info}>
        <p className={styles.timestamp}>{formatTimestamp(gallery.timestamp)}</p>
      </div>
    </div>
  );
}

GalleryPreview.propTypes = {
  gallery: PropTypes.shape({
    id: PropTypes.string.isRequired,
    timestamp: PropTypes.string.isRequired,
    preview: PropTypes.string,
    imageCount: PropTypes.number,
  }).isRequired,
  isSelected: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
};

GalleryPreview.defaultProps = {
  isSelected: false,
};

// Memoize component to prevent re-renders when other gallery items update
// Only re-renders when this specific gallery's data changes
export default memo(GalleryPreview);
