/**
 * Correlation ID Utility
 * Generates and manages UUIDs for request tracing
 */

import { v4 as uuidv4 } from 'uuid';

/**
 * Generate a new correlation ID
 */
export function generateCorrelationId(): string {
  return uuidv4();
}

/**
 * Store for current correlation ID (for batching)
 */
let currentCorrelationId: string | null = null;

/**
 * Get or create correlation ID for current context
 */
export function getCorrelationId(): string {
  if (!currentCorrelationId) {
    currentCorrelationId = generateCorrelationId();
  }
  return currentCorrelationId;
}

/**
 * Clear current correlation ID (start new context)
 */
export function clearCorrelationId(): void {
  currentCorrelationId = null;
}

/**
 * Set a specific correlation ID
 */
export function setCorrelationId(id: string): void {
  currentCorrelationId = id;
}
