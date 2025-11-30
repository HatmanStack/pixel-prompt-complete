/**
 * useMemoizedCallback Hook
 * DEPRECATED: Use useCallback directly instead
 * This wrapper provides no benefit over useCallback
 */

import { useCallback } from 'react';

/**
 * Creates a memoized callback function
 * @deprecated Use useCallback directly
 * @param {Function} callback - The callback function to memoize
 * @param {Array} deps - Dependency array for the callback
 * @returns {Function} Memoized callback
 */
function useMemoizedCallback(callback, deps) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useCallback(callback, deps);
}

export default useMemoizedCallback;
