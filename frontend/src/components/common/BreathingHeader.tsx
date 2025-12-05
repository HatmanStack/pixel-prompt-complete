/**
 * BreathingHeader Component
 * Animated "PIXEL PROMPT" header with staggered breathing effect per character
 * Creates a smooth wave-like animation across the title
 */

import type { FC } from 'react';

interface BreathingHeaderProps {
  className?: string;
}

const TITLE = 'PIXEL PROMPT';
const ANIMATION_DURATION = 4000; // 4s for smooth, organic feel

/**
 * Calculate stagger delay for each character using a sine wave pattern
 * Creates a more natural, organic breathing wave effect
 */
function getCharacterDelay(index: number, total: number): string {
  // Use sine wave to create smooth stagger - characters in middle breathe together
  const normalizedPosition = index / (total - 1);
  // Spread delays across 2.5s to avoid too much overlap while keeping wave visible
  const delayMs = Math.sin(normalizedPosition * Math.PI * 0.5) * 2500;
  return `${Math.round(delayMs)}ms`;
}

export const BreathingHeader: FC<BreathingHeaderProps> = ({ className = '' }) => {
  const characters = TITLE.split('');

  return (
    <h1
      className={`
        flex items-center justify-center flex-wrap gap-0.5
        font-display text-accent
        text-3xl sm:text-4xl md:text-5xl lg:text-6xl
        select-none
        ${className}
      `}
      aria-label={TITLE}
    >
      {characters.map((char, index) => (
        <span
          key={`${char}-${index}`}
          className={`
            inline-block
            animate-[letter-breathe_${ANIMATION_DURATION}ms_ease-in-out_infinite]
            motion-reduce:animate-none
            ${char === ' ' ? 'w-3 sm:w-4 md:w-5' : ''}
          `}
          style={{
            animationDelay: getCharacterDelay(index, characters.length),
            animationDuration: `${ANIMATION_DURATION}ms`,
          }}
          aria-hidden="true"
        >
          {char === ' ' ? '\u00A0' : char}
        </span>
      ))}
    </h1>
  );
};

export default BreathingHeader;
