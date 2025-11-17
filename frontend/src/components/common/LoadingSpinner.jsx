/**
 * LoadingSpinner Component
 * Simple loading spinner for React.Suspense fallback
 */

import styles from './LoadingSpinner.module.css';

function LoadingSpinner({ message = 'Loading...' }) {
  return (
    <div className={styles.container}>
      <div className={styles.spinner} role="status" aria-label="Loading">
        <div className={styles.spinnerCircle}></div>
      </div>
      {message && <p className={styles.message}>{message}</p>}
    </div>
  );
}

export default LoadingSpinner;
