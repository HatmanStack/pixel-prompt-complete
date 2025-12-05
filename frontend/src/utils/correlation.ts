/**
 * Correlation ID Utility
 * Generates UUIDs for request tracing
 */

import { v4 as uuidv4 } from 'uuid';

/**
 * Generate a new correlation ID
 */
export function generateCorrelationId(): string {
  return uuidv4();
}
