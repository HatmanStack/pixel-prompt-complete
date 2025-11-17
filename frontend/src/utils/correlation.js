/**
 * Correlation ID Utility
 * Generates and manages UUIDs for request tracing
 */

import { v4 as uuidv4 } from 'uuid';

/**
 * Generate a new correlation ID
 * @returns {string} UUIDv4 string
 */
export function generateCorrelationId() {
  return uuidv4();
}

/**
 * Store for current correlation ID (for batching)
 */
let currentCorrelationId = null;

/**
 * Get or create correlation ID for current context
 * @returns {string} Correlation ID
 */
export function getCorrelationId() {
  if (!currentCorrelationId) {
    currentCorrelationId = generateCorrelationId();
  }
  return currentCorrelationId;
}

/**
 * Clear current correlation ID (start new context)
 */
export function clearCorrelationId() {
  currentCorrelationId = null;
}

/**
 * Set a specific correlation ID
 * @param {string} id - Correlation ID to set
 */
export function setCorrelationId(id) {
  currentCorrelationId = id;
}
