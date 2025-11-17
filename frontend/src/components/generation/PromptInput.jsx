/**
 * PromptInput Component
 * Textarea input for entering image generation prompts
 */

import { useRef, useEffect } from 'react';
import styles from './PromptInput.module.css';

function PromptInput({
  value,
  onChange,
  onClear,
  maxLength = 500,
  placeholder = "Describe the image you want to generate...",
  disabled = false
}) {
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [value]);

  const handleChange = (e) => {
    const newValue = e.target.value;

    // Enforce max length
    if (newValue.length <= maxLength) {
      onChange(newValue);
    }
  };

  const handleClear = () => {
    // Confirm before clearing if prompt is long
    if (value.length > 50) {
      if (!window.confirm('Are you sure you want to clear this prompt?')) {
        return;
      }
    }
    onClear();
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    // Escape key: Clear input
    if (e.key === 'Escape') {
      handleClear();
    }

    // Ctrl/Cmd + Enter: Could trigger generation (handled by parent)
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      // Dispatch custom event that parent can listen to
      const event = new CustomEvent('generate-trigger');
      document.dispatchEvent(event);
    }
  };

  const remainingChars = maxLength - value.length;
  const isNearLimit = remainingChars < 50;

  return (
    <div className={styles.container}>
      <div className={styles.inputWrapper}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          aria-label="Image prompt"
        />

        {value && !disabled && (
          <button
            className={styles.clearButton}
            onClick={handleClear}
            aria-label="Clear prompt"
            type="button"
          >
            ✕
          </button>
        )}
      </div>

      <div className={styles.footer}>
        <span
          className={`${styles.charCount} ${isNearLimit ? styles.warning : ''}`}
          aria-live="polite"
        >
          {value.length} / {maxLength}
        </span>

        <span className={styles.hint}>
          Press Ctrl+Enter to generate • Esc to clear
        </span>
      </div>
    </div>
  );
}

export default PromptInput;
