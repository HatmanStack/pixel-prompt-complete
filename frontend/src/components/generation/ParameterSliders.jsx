/**
 * ParameterSliders Component
 * Sliders for adjusting generation parameters (steps, guidance)
 */

import styles from './ParameterSliders.module.css';

function ParameterSliders({
  steps,
  guidance,
  onStepsChange,
  onGuidanceChange,
  disabled = false
}) {
  const handleStepsChange = (e) => {
    const value = parseInt(e.target.value, 10);
    onStepsChange(value);
  };

  const handleGuidanceChange = (e) => {
    const value = parseFloat(e.target.value);
    // Round to nearest 0.5
    const rounded = Math.round(value * 2) / 2;
    onGuidanceChange(rounded);
  };

  // Calculate percentage for fill effect
  const stepsPercent = ((steps - 3) / (50 - 3)) * 100;
  const guidancePercent = (guidance / 10) * 100;

  return (
    <div className={styles.container}>
      {/* Steps Slider */}
      <div className={styles.sliderGroup}>
        <div className={styles.label}>
          <span>Sampling Steps</span>
          <span className={styles.value}>{steps}</span>
        </div>
        <div className={styles.sliderWrapper}>
          <input
            type="range"
            min="3"
            max="50"
            step="1"
            value={steps}
            onChange={handleStepsChange}
            disabled={disabled}
            className={styles.slider}
            style={{
              '--fill-percent': `${stepsPercent}%`
            }}
            aria-label="Sampling steps"
          />
          <div className={styles.markers}>
            <span>3</span>
            <span>28</span>
            <span>50</span>
          </div>
        </div>
        <p className={styles.description}>
          Higher values = more refined images (slower)
        </p>
      </div>

      {/* Guidance Slider */}
      <div className={styles.sliderGroup}>
        <div className={styles.label}>
          <span>Guidance Scale</span>
          <span className={styles.value}>{guidance.toFixed(1)}</span>
        </div>
        <div className={styles.sliderWrapper}>
          <input
            type="range"
            min="0"
            max="10"
            step="0.5"
            value={guidance}
            onChange={handleGuidanceChange}
            disabled={disabled}
            className={styles.slider}
            style={{
              '--fill-percent': `${guidancePercent}%`
            }}
            aria-label="Guidance scale"
          />
          <div className={styles.markers}>
            <span>0</span>
            <span>5</span>
            <span>10</span>
          </div>
        </div>
        <p className={styles.description}>
          Higher values = closer adherence to prompt
        </p>
      </div>
    </div>
  );
}

export default ParameterSliders;
