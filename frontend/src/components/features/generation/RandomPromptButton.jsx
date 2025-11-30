/**
 * RandomPromptButton Component
 * Button that populates prompt input with random seed prompts
 * Helps users get started and explore different styles
 * Supports Ctrl+R keyboard shortcut
 */

import { useState, useEffect, useCallback } from 'react';
import { getRandomPrompt } from '../../../data/seedPrompts';
import styles from './RandomPromptButton.module.css';

function RandomPromptButton({ onSelectPrompt, disabled = false }) {
  const [lastPrompt, setLastPrompt] = useState(null);
  const [isAnimating, setIsAnimating] = useState(false);

  // Shared logic for triggering random prompt
  const triggerRandomPrompt = useCallback(() => {
    if (disabled) return;

    // Trigger animation
    setIsAnimating(true);
    setTimeout(() => setIsAnimating(false), 300);

    // Get random prompt (avoiding consecutive duplicates)
    const randomPrompt = getRandomPrompt(lastPrompt);
    setLastPrompt(randomPrompt);
    onSelectPrompt(randomPrompt);
  }, [disabled, lastPrompt, onSelectPrompt]);

  const handleClick = () => {
    triggerRandomPrompt();
  };

  // Listen for keyboard shortcut (Ctrl+R)
  useEffect(() => {
    document.addEventListener('random-prompt-trigger', triggerRandomPrompt);
    return () => {
      document.removeEventListener('random-prompt-trigger', triggerRandomPrompt);
    };
  }, [triggerRandomPrompt]);

  return (
    <button
      className={`${styles.button} ${isAnimating ? styles.animating : ''}`}
      onClick={handleClick}
      disabled={disabled}
      aria-label="Get random prompt inspiration"
      title="Random Prompt (Ctrl+R)"
    >
      <span className={styles.icon}>🎲</span>
      <span className={styles.text}>Inspire Me</span>
    </button>
  );
}

export default RandomPromptButton;
