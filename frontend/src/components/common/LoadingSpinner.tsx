/**
 * LoadingSpinner Component
 * Animated spinner with playful bounce effect and size variants
 */

import type { FC } from 'react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
  className?: string;
}

const sizeStyles: Record<string, string> = {
  sm: 'w-4 h-4 border-2',
  md: 'w-8 h-8 border-4',
  lg: 'w-12 h-12 border-4',
};

export const LoadingSpinner: FC<LoadingSpinnerProps> = ({
  size = 'md',
  message = 'Loading...',
  className = '',
}) => {
  return (
    <div
      className={`
        flex flex-col items-center justify-center gap-3
        ${className}
      `}
      role="status"
      aria-busy="true"
      aria-live="polite"
    >
      <div
        className={`
          ${sizeStyles[size]}
          border-accent/30 border-t-accent
          rounded-full
          animate-[spinBounce_1s_ease-in-out_infinite]
          motion-reduce:animate-none motion-reduce:border-accent
        `}
        aria-hidden="true"
      />
      {message && (
        <p
          className="text-sm text-text-secondary animate-[gentlePulse_2s_ease-in-out_infinite] motion-reduce:animate-none"
          aria-live="polite"
        >
          {message}
        </p>
      )}
    </div>
  );
};

export default LoadingSpinner;
