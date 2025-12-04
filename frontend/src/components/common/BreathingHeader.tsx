/**
 * BreathingHeader Component
 * Animated "PIXEL PROMPT" header with staggered breathing effect per character
 */

import type { FC } from 'react';

interface BreathingHeaderProps {
  className?: string;
}

const TITLE = 'PIXEL PROMPT';

/**
 * Calculate stagger delay for each character
 * Creates a wave-like breathing effect
 */
function getCharacterDelay(index: number, total: number): string {
  // Distribute delays across the animation duration
  const delayMs = (index / total) * 2000; // 2s total spread
  return `${delayMs}ms`;
}

export const BreathingHeader: FC<BreathingHeaderProps> = ({ className = '' }) => {
  const characters = TITLE.split('');

  return (
    <h1
      className={`
        flex items-center justify-center flex-wrap
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
            animate-[letter-breathe_3s_ease-in-out_infinite]
            motion-reduce:animate-none
            ${char === ' ' ? 'w-4 sm:w-6' : ''}
          `}
          style={{
            animationDelay: getCharacterDelay(index, characters.length),
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
