/**
 * RandomPromptButton Component
 * Button that populates prompt input with random seed prompts
 * Helps users get started and explore different styles
 * Supports Ctrl+R keyboard shortcut
 */

import { useState, useEffect, useCallback, type FC } from 'react';
import { getRandomPrompt, type SeedPrompt } from '@/data/seedPrompts';
import { useAppStore } from '@/stores/useAppStore';
import { useSound } from '@/hooks/useSound';

interface RandomPromptButtonProps {
  disabled?: boolean;
}

export const RandomPromptButton: FC<RandomPromptButtonProps> = ({ disabled = false }) => {
  const { setPrompt } = useAppStore();
  const { playSound } = useSound();

  const [lastPrompt, setLastPrompt] = useState<SeedPrompt | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);

  // Shared logic for triggering random prompt
  const triggerRandomPrompt = useCallback(() => {
    if (disabled) return;

    // Trigger animation
    setIsAnimating(true);
    setTimeout(() => setIsAnimating(false), 300);

    // Play sound
    playSound('switch');

    // Get random prompt (avoiding consecutive duplicates)
    const randomPrompt = getRandomPrompt(lastPrompt);
    setLastPrompt(randomPrompt);
    setPrompt(randomPrompt);
  }, [disabled, lastPrompt, setPrompt, playSound]);

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
      className={`
        flex items-center gap-1.5
        py-2 px-4
        bg-gradient-to-br from-accent-muted to-accent
        border-none rounded-md
        text-white text-sm font-medium
        cursor-pointer
        shadow-md
        transition-all duration-300
        hover:-translate-y-0.5 hover:shadow-lg
        active:translate-y-0
        disabled:opacity-50 disabled:cursor-not-allowed
        focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
        md:w-auto w-full justify-center
      `}
      onClick={handleClick}
      disabled={disabled}
      aria-label="Get random prompt inspiration"
      title="Random Prompt (Ctrl+R)"
    >
      <span className={`text-lg leading-none transition-transform duration-300 ${isAnimating ? 'animate-spin' : ''}`}>
        🎲
      </span>
      <span className="whitespace-nowrap">Inspire Me</span>
    </button>
  );
};

export default RandomPromptButton;
