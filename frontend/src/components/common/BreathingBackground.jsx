/**
 * BreathingBackground Component
 * Subtle animated background gradient that "breathes"
 */

import { useState } from 'react';
import styles from './BreathingBackground.module.css';

function BreathingBackground() {
  const [isEnabled] = useState(() => {
    const saved = localStorage.getItem('breathingBackgroundEnabled');
    return saved === null ? true : saved === 'true';
  });

  // Don't render if disabled
  if (!isEnabled) {
    return null;
  }

  return (
    <div className={styles.breathingBackground} aria-hidden="true">
      <div className={styles.gradient1} />
      <div className={styles.gradient2} />
      <div className={styles.gradient3} />
    </div>
  );
}

// Export toggle control component
export function BreathingBackgroundToggle() {
  const [isEnabled, setIsEnabled] = useState(() => {
    const saved = localStorage.getItem('breathingBackgroundEnabled');
    return saved === null ? true : saved === 'true';
  });

  const handleToggle = () => {
    const newValue = !isEnabled;
    setIsEnabled(newValue);
    localStorage.setItem('breathingBackgroundEnabled', newValue.toString());
    // Force re-render of BreathingBackground by dispatching event
    window.dispatchEvent(new Event('storage'));
  };

  return (
    <button
      onClick={handleToggle}
      className={styles.toggleButton}
      aria-label={`${isEnabled ? 'Disable' : 'Enable'} breathing background animation`}
      type="button"
    >
      {isEnabled ? '🌊 Animation On' : '⏸ Animation Off'}
    </button>
  );
}

export default BreathingBackground;
