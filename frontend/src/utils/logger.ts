/**
 * Error Logging Client
 * Sends frontend errors to backend /log endpoint for CloudWatch logging
 */

import { API_BASE_URL } from '@/api/config';
import { generateCorrelationId } from './correlation';

/**
 * Log levels
 */
export const LogLevel = {
  ERROR: 'ERROR',
  WARNING: 'WARNING',
  INFO: 'INFO',
  DEBUG: 'DEBUG',
} as const;

type LogLevelType = (typeof LogLevel)[keyof typeof LogLevel];

interface LogPayload {
  level: LogLevelType;
  message: string;
  stack?: string;
  metadata: Record<string, unknown>;
}

interface LogOptions {
  error?: Error | null;
  correlationId?: string;
  metadata?: Record<string, unknown>;
}

interface LogContext {
  correlationId?: string;
  [key: string]: unknown;
}

/**
 * Deduplication cache
 */
const errorCache = new Map<string, number>();
const DEDUP_WINDOW_MS = 60000; // 1 minute

/**
 * Generate hash for error deduplication
 */
function generateErrorHash(message: string, stack: string): string {
  const stackFirstLine = stack ? stack.split('\n')[0] : '';
  return `${message}:${stackFirstLine}`;
}

/**
 * Check if error should be deduplicated
 */
function shouldDeduplicate(hash: string): boolean {
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
function cleanupErrorCache(): void {
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
 */
export function serializeError(error: Error | null | undefined): {
  message: string;
  stack: string;
  name: string;
} {
  if (!error) return { message: '', stack: '', name: 'Error' };

  return {
    message: error.message || String(error),
    stack: error.stack || '',
    name: error.name || 'Error',
  };
}

/**
 * Get browser metadata
 */
export function getBrowserMetadata(): Record<string, string> {
  return {
    userAgent: navigator.userAgent,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    url: window.location.href,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Send log to backend endpoint
 */
export async function sendLog(
  level: LogLevelType,
  message: string,
  options: LogOptions = {}
): Promise<void> {
  const { error, correlationId = generateCorrelationId(), metadata = {} } = options;

  // Build log payload
  const payload: LogPayload = {
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
    console.warn('Error sending log to backend:', err instanceof Error ? err.message : err);
  }
}

/**
 * Log an error
 */
export function logError(
  message: string,
  error: Error | null = null,
  context: LogContext = {}
): Promise<void> {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.ERROR, message, {
    error,
    correlationId,
    metadata,
  });
}

/**
 * Log a warning
 */
export function logWarning(message: string, context: LogContext = {}): Promise<void> {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.WARNING, message, {
    correlationId,
    metadata,
  });
}

/**
 * Log an info message
 */
export function logInfo(message: string, context: LogContext = {}): Promise<void> {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.INFO, message, {
    correlationId,
    metadata,
  });
}

/**
 * Log a debug message
 */
export function logDebug(message: string, context: LogContext = {}): Promise<void> {
  const { correlationId, ...metadata } = context;

  return sendLog(LogLevel.DEBUG, message, {
    correlationId,
    metadata,
  });
}
