/**
 * useBreakpoint Hook
 * Detects current responsive breakpoint using matchMedia
 */

import { useState, useEffect } from 'react';

export type Breakpoint = 'sm' | 'md' | 'lg' | 'xl';

const breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
};

/**
 * Get current breakpoint based on window width
 */
function getBreakpoint(width: number): Breakpoint {
  if (width >= breakpoints.xl) return 'xl';
  if (width >= breakpoints.lg) return 'lg';
  if (width >= breakpoints.md) return 'md';
  return 'sm';
}

/**
 * Custom hook for responsive breakpoint detection
 * @returns Current breakpoint and helper booleans
 */
export function useBreakpoint() {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() => {
    if (typeof window === 'undefined') return 'lg';
    return getBreakpoint(window.innerWidth);
  });

  useEffect(() => {
    // Create media query lists for each breakpoint
    const mediaQueries = {
      sm: window.matchMedia(`(min-width: ${breakpoints.sm}px)`),
      md: window.matchMedia(`(min-width: ${breakpoints.md}px)`),
      lg: window.matchMedia(`(min-width: ${breakpoints.lg}px)`),
      xl: window.matchMedia(`(min-width: ${breakpoints.xl}px)`),
    };

    const handleChange = () => {
      setBreakpoint(getBreakpoint(window.innerWidth));
    };

    // Add listeners
    Object.values(mediaQueries).forEach((mq) => {
      mq.addEventListener('change', handleChange);
    });

    // Set initial value
    handleChange();

    // Cleanup
    return () => {
      Object.values(mediaQueries).forEach((mq) => {
        mq.removeEventListener('change', handleChange);
      });
    };
  }, []);

  return {
    breakpoint,
    isMobile: breakpoint === 'sm' || breakpoint === 'md',
    isDesktop: breakpoint === 'lg' || breakpoint === 'xl',
    isSmall: breakpoint === 'sm',
    isMedium: breakpoint === 'md',
    isLarge: breakpoint === 'lg',
    isExtraLarge: breakpoint === 'xl',
  };
}

export default useBreakpoint;
