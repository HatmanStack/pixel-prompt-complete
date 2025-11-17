/**
 * GenerateButton Component
 * Main button for triggering image generation
 */

import styles from './GenerateButton.module.css';

function GenerateButton({
  onClick,
  isGenerating = false,
  disabled = false,
  label = "Generate Images"
}) {
  const handleClick = () => {
    if (!disabled && !isGenerating) {
      onClick();
    }
  };

  const getButtonText = () => {
    if (isGenerating) {
      return "Generating...";
    }
    return label;
  };

  return (
    <button
      className={`${styles.button} ${isGenerating ? styles.generating : ''}`}
      onClick={handleClick}
      disabled={disabled || isGenerating}
      aria-label={getButtonText()}
      aria-busy={isGenerating}
      type="button"
    >
      {isGenerating && (
        <span className={styles.spinner} aria-hidden="true">
          <svg className={styles.spinnerSvg} viewBox="0 0 24 24">
            <circle
              className={styles.spinnerCircle}
              cx="12"
              cy="12"
              r="10"
              fill="none"
              strokeWidth="3"
            />
          </svg>
        </span>
      )}
      <span className={styles.text}>{getButtonText()}</span>
    </button>
  );
}

export default GenerateButton;
