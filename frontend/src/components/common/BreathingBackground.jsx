/**
 * BreathingBackground Component
 * Subtle animated background gradient that "breathes"
 */

import { useState, useEffect } from 'react';
import styles from './BreathingBackground.module.css';

function BreathingBackground() {
  const [isEnabled, setIsEnabled] = useState(() => {
    // Load preference from localStorage
    const saved = localStorage.getItem('breathingBackgroundEnabled');
    // Default to enabled if not set
    return saved === null ? true : saved === 'true';
  });

  // Save preference to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('breathingBackgroundEnabled', isEnabled.toString());
  }, [isEnabled]);

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
