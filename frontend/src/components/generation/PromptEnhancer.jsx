/**
 * PromptEnhancer Component
 * UI for prompt enhancement feature
 * Supports Ctrl+E keyboard shortcut
 */

import { useState, useEffect } from 'react';
import { enhancePrompt } from '../../api/client';
import styles from './PromptEnhancer.module.css';

function PromptEnhancer({ currentPrompt = '', onUsePrompt, disabled = false }) {
  const [isEnhancing, setIsEnhancing] = useState(false);
  const [enhancedPrompt, setEnhancedPrompt] = useState(null);
  const [error, setError] = useState(null);
  const [showLong, setShowLong] = useState(false);

  // Listen for keyboard shortcut (Ctrl+E)
  useEffect(() => {
    const handleEnhancePromptTrigger = () => {
      if (!disabled && !isEnhancing && currentPrompt.trim()) {
        handleEnhance();
      }
    };

    document.addEventListener('enhance-prompt-trigger', handleEnhancePromptTrigger);
    return () => {
      document.removeEventListener('enhance-prompt-trigger', handleEnhancePromptTrigger);
    };
  }, [disabled, isEnhancing, currentPrompt]);

  const handleEnhance = async () => {
    if (!currentPrompt.trim()) {
      setError('Please enter a prompt first');
      return;
    }

    setIsEnhancing(true);
    setError(null);
    setEnhancedPrompt(null);

    try {
      const response = await enhancePrompt(currentPrompt);

      if (response.short_prompt || response.long_prompt) {
        setEnhancedPrompt({
          short: response.short_prompt || currentPrompt,
          long: response.long_prompt || response.short_prompt || currentPrompt,
          original: currentPrompt,
        });
      } else {
        throw new Error('No enhanced prompt received');
      }
    } catch (err) {
      console.error('Enhancement error:', err);
      setError(err.message || 'Failed to enhance prompt');
    } finally {
      setIsEnhancing(false);
    }
  };

  const handleUse = () => {
    const promptToUse = showLong ? enhancedPrompt.long : enhancedPrompt.short;
    onUsePrompt(promptToUse);
    setEnhancedPrompt(null);
  };

  const handleDiscard = () => {
    setEnhancedPrompt(null);
    setError(null);
  };

  return (
    <div className={styles.container}>
      {!enhancedPrompt ? (
        <button
          className={styles.enhanceButton}
          onClick={handleEnhance}
          disabled={disabled || isEnhancing || !currentPrompt.trim()}
          type="button"
        >
          {isEnhancing ? (
            <>
              <span className={styles.spinner} />
              <span>Enhancing...</span>
            </>
          ) : (
            <>
              <span className={styles.icon}>✨</span>
              <span>Enhance Prompt</span>
            </>
          )}
        </button>
      ) : (
        <div className={styles.result}>
          <div className={styles.resultHeader}>
            <h4>Enhanced Prompt</h4>
            <div className={styles.toggle}>
              <button
                className={`${styles.toggleButton} ${!showLong ? styles.active : ''}`}
                onClick={() => setShowLong(false)}
                type="button"
              >
                Short
              </button>
              <button
                className={`${styles.toggleButton} ${showLong ? styles.active : ''}`}
                onClick={() => setShowLong(true)}
                type="button"
              >
                Long
              </button>
            </div>
          </div>

          <div className={styles.comparison}>
            <div className={styles.promptBox}>
              <label>Original:</label>
              <p>{enhancedPrompt.original}</p>
            </div>

            <div className={styles.promptBox}>
              <label>Enhanced:</label>
              <p className={styles.enhanced}>
                {showLong ? enhancedPrompt.long : enhancedPrompt.short}
              </p>
            </div>
          </div>

          <div className={styles.actions}>
            <button
              className={styles.useButton}
              onClick={handleUse}
              type="button"
            >
              Use This
            </button>
            <button
              className={styles.discardButton}
              onClick={handleDiscard}
              type="button"
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className={styles.error}>
          <span className={styles.errorIcon}>⚠</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

export default PromptEnhancer;
