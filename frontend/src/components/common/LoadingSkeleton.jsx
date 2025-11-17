/**
 * LoadingSkeleton Component
 * Animated loading placeholder for better UX
 */

import styles from './LoadingSkeleton.module.css';

function LoadingSkeleton({ width = '100%', height = '20px', variant = 'rect', className = '' }) {
  const skeletonClass = variant === 'circle' ? styles.circle : styles.rect;

  return (
    <div
      className={`${styles.skeleton} ${skeletonClass} ${className}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export default LoadingSkeleton;
