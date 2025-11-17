/**
 * useMemoizedCallback Hook
 * Wrapper around useCallback for common use cases
 * Simplifies callback memoization across components
 */

import { useCallback } from 'react';

/**
 * Creates a memoized callback function
 * @param {Function} callback - The callback function to memoize
 * @param {Array} deps - Dependency array for the callback
 * @returns {Function} Memoized callback
 */
function useMemoizedCallback(callback, deps = []) {
  return useCallback(callback, deps);
}

export default useMemoizedCallback;
