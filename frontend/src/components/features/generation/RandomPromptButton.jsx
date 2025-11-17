/**
 * RandomPromptButton Component
 * Button that populates prompt input with random seed prompts
 * Helps users get started and explore different styles
 * Supports Ctrl+R keyboard shortcut
 */

import { useState, useEffect } from 'react';
import { getRandomPrompt } from '../../../data/seedPrompts';
import styles from './RandomPromptButton.module.css';

function RandomPromptButton({ onSelectPrompt, disabled = false }) {
  const [lastPrompt, setLastPrompt] = useState(null);
  const [isAnimating, setIsAnimating] = useState(false);

  const handleClick = () => {
    if (disabled) return;

    // Trigger animation
    setIsAnimating(true);
    setTimeout(() => setIsAnimating(false), 300);

    // Get random prompt (avoiding consecutive duplicates)
    const randomPrompt = getRandomPrompt(lastPrompt);
    setLastPrompt(randomPrompt);
    onSelectPrompt(randomPrompt);
  };

  // Listen for keyboard shortcut (Ctrl+R)
  useEffect(() => {
    const handleRandomPromptTrigger = () => {
      handleClick();
    };

    document.addEventListener('random-prompt-trigger', handleRandomPromptTrigger);
    return () => {
      document.removeEventListener('random-prompt-trigger', handleRandomPromptTrigger);
    };
  }, [disabled, lastPrompt]); // Re-create listener when disabled or lastPrompt changes

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
