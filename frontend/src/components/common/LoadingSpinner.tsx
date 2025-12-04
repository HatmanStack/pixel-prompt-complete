/**
 * LoadingSpinner Component
 * Animated spinner with size variants
 */

import type { FC } from 'react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
  className?: string;
}

const sizeStyles: Record<string, string> = {
  sm: 'w-4 h-4',
  md: 'w-8 h-8',
  lg: 'w-12 h-12',
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
    >
      <div
        className={`
          ${sizeStyles[size]}
          border-4 border-accent/30 border-t-accent
          rounded-full
          animate-spin
          motion-reduce:animate-none motion-reduce:border-accent
        `}
        role="status"
        aria-label="Loading"
      />
      {message && (
        <p className="text-sm text-text-secondary animate-pulse motion-reduce:animate-none">
          {message}
        </p>
      )}
    </div>
  );
};

export default LoadingSpinner;
