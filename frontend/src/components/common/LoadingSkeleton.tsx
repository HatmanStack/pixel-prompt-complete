/**
 * LoadingSkeleton Component
 * Animated loading placeholder with shape variants
 */

import type { FC } from 'react';

interface LoadingSkeletonProps {
  width?: string | number;
  height?: string | number;
  shape?: 'rectangle' | 'circle' | 'text';
  className?: string;
}

export const LoadingSkeleton: FC<LoadingSkeletonProps> = ({
  width = '100%',
  height = '20px',
  shape = 'rectangle',
  className = '',
}) => {
  const shapeStyles: Record<string, string> = {
    rectangle: 'rounded-md',
    circle: 'rounded-full',
    text: 'rounded',
  };

  // For text shape, default to a reasonable text-like height
  const effectiveHeight = shape === 'text' ? (height === '20px' ? '1em' : height) : height;

  return (
    <div
      className={`
        bg-secondary/50
        animate-pulse
        motion-reduce:animate-none motion-reduce:bg-secondary
        ${shapeStyles[shape]}
        ${className}
      `}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof effectiveHeight === 'number' ? `${effectiveHeight}px` : effectiveHeight,
      }}
      aria-hidden="true"
    />
  );
};

export default LoadingSkeleton;
