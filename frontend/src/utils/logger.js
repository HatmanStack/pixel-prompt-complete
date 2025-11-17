/**
 * Error Logging Client
 * Sends frontend errors to backend /log endpoint for CloudWatch logging
 */

import { API_BASE_URL } from '../api/config';
import { generateCorrelationId } from './correlation';

/**
 * Log levels
 */
export const LogLevel = {
  ERROR: 'ERROR',
  WARNING: 'WARNING',
  INFO: 'INFO',
  DEBUG: 'DEBUG',
};

/**
 * Deduplication cache
 * Stores error hashes to prevent duplicate logging within time window
 */
const errorCache = new Map();
const DEDUP_WINDOW_MS = 60000; // 1 minute

/**
 * Generate hash for error deduplication
 * @param {string} message - Error message
 * @param {string} stack - Error stack trace
 * @returns {string} Hash string
 */
function generateErrorHash(message, stack) {
  // Simple hash based on message and first line of stack
  const stackFirstLine = stack ? stack.split('\n')[0] : '';
  return `${message}:${stackFirstLine}`;
}

/**
 * Check if error should be deduplicated
 * @param {string} hash - Error hash
 * @returns {boolean} True if error was recently logged
 */
function shouldDeduplicate(hash) {
  const lastLogged = errorCache.get(hash);
  if (lastLogged && Date.now() - lastLogged < DEDUP_WINDOW_MS) {
    return true;
  }
  errorCache.set(hash, Date.now());
  return false;
}

/**
 * Clean up old entries from error cache
 */
function cleanupErrorCache() {
  const now = Date.now();
  for (const [hash, timestamp] of errorCache.entries()) {
    if (now - timestamp > DEDUP_WINDOW_MS) {
      errorCache.delete(hash);
    }
  }
}

// Cleanup cache periodically
setInterval(cleanupErrorCache, DEDUP_WINDOW_MS);

/**
 * Serialize error object to loggable format
 * @param {Error} error - Error object
 * @returns {Object} Serialized error
 */
function serializeError(error) {
  if (!error) return {};

  return {
    message: error.message || String(error),
    stack: error.stack || '',
    name: error.name || 'Error',
  };
}

/**
 * Get browser metadata
 * @returns {Object} Browser information
 */
function getBrowserMetadata() {
  return {
    userAgent: navigator.userAgent,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    url: window.location.href,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Send log to backend endpoint
 * @param {string} level - Log level
 * @param {string} message - Log message
 * @param {Object} options - Additional options
 * @returns {Promise<void>}
 */
async function sendLog(level, message, options = {}) {
  const {
    error,
    correlationId = generateCorrelationId(),
    metadata = {},
  } = options;

  // Build log payload
  const payload = {
    level,
    message,
    metadata: {
      ...getBrowserMetadata(),
      ...metadata,
    },
  };

  // Add error details if provided
  if (error) {
    const serialized = serializeError(error);
    payload.stack = serialized.stack;
    payload.metadata.errorName = serialized.name;
  }

  // Check deduplication for errors
  if (level === LogLevel.ERROR && payload.stack) {
    const hash = generateErrorHash(message, payload.stack);
    if (shouldDeduplicate(hash)) {
      console.debug('Skipping duplicate error log:', message);
      return;
    }
  }

  try {
    // Send to backend /log endpoint
    const response = await fetch(`${API_BASE_URL}/log`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': correlationId,
      },
      body: JSON.stringify(payload),
    });

    // Don't throw on logging failure - fail silently
    if (!response.ok) {
      console.warn('Failed to send log to backend:', response.status);
    }
  } catch (err) {
    // Fail silently - logging failure should not crash app
    console.warn('Error sending log to backend:', err.message);
  }
}

/**
 * Log an error
 * @param {string} message - Error message
 * @param {Error|Object} error - Error object
 * @param {Object} context - Additional context
 */
export function logError(message, error = null, context = {}) {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.ERROR, message, {
    error,
    correlationId,
    metadata,
  });
}

/**
 * Log a warning
 * @param {string} message - Warning message
 * @param {Object} context - Additional context
 */
export function logWarning(message, context = {}) {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.WARNING, message, {
    correlationId,
    metadata,
  });
}

/**
 * Log an info message
 * @param {string} message - Info message
 * @param {Object} context - Additional context
 */
export function logInfo(message, context = {}) {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.INFO, message, {
    correlationId,
    metadata,
  });
}

/**
 * Log a debug message
 * @param {string} message - Debug message
 * @param {Object} context - Additional context
 */
export function logDebug(message, context = {}) {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.DEBUG, message, {
    correlationId,
    metadata,
  });
}

// Export for testing
export { sendLog, serializeError, getBrowserMetadata };
