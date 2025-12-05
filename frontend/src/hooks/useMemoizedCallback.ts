/**
 * useMemoizedCallback Hook
 * DEPRECATED: Use useCallback directly instead
 * This wrapper provides no benefit over useCallback
 */

import { useCallback, type DependencyList } from 'react';

/**
 * Creates a memoized callback function
 * @deprecated Use useCallback directly
 */
function useMemoizedCallback<T extends (...args: unknown[]) => unknown>(
  callback: T,
  deps: DependencyList
): T {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useCallback(callback, deps) as T;
}

export default useMemoizedCallback;
