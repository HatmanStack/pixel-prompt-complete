/**
 * Client-side error reporting.
 *
 * The app's entire client-side error strategy was `console.error`. For a
 * static SPA served from a CDN that is not an observability channel: a
 * production crash is visible only in the browser that suffered it, and the
 * backend's `/log` endpoint — with a handler and full test coverage — sat
 * unused on the other side of the API.
 *
 * This deliberately uses `fetch` directly rather than `apiFetch`. `apiFetch`
 * retries, raises toasts and can trigger an auth redirect on a 401, none of
 * which belong in a crash reporter: a reporter that redirects the page is a
 * reporter that destroys the evidence.
 */

import { API_BASE_URL, API_ROUTES } from './config';

export type LogLevel = 'ERROR' | 'WARNING' | 'INFO' | 'DEBUG';

/**
 * The backend rejects a body larger than this with a 413
 * (`MAX_LOG_BODY_SIZE` in `backend/src/lambda_function.py`). It is **10 KB**,
 * not the 1 MB an API Gateway payload allows, and a React `componentStack`
 * for a deep tree exceeds it unaided — so an untruncated report is not a
 * large report, it is no report at all.
 */
export const MAX_LOG_BODY_BYTES = 10 * 1024;

/** Leaves room for the JSON envelope, the level, the message and metadata. */
const STACK_LIMIT = 4096;
const MESSAGE_LIMIT = 1024;

export interface ReportErrorOptions {
  /** A stack or React `componentStack`. Truncated to fit the body limit. */
  stack?: string;
  /**
   * Extra context. Note that `timestamp`, `level`, `correlation_id` and
   * `message` are stripped server-side, so do not rely on them surviving.
   */
  metadata?: Record<string, unknown>;
  /** Sent as `X-Correlation-ID` so the client and server records share an id. */
  correlationId?: string;
}

function truncate(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit)}... [truncated]`;
}

/**
 * Report a client-side error to the backend. Fire-and-forget.
 *
 * Never throws and never rejects. An error reporter that throws inside an
 * error boundary loses the original error — the one thing it exists to
 * preserve — so every failure mode here is swallowed.
 */
export async function reportError(
  level: LogLevel,
  message: string,
  options: ReportErrorOptions = {},
): Promise<void> {
  try {
    const body: Record<string, unknown> = {
      level,
      message: truncate(message, MESSAGE_LIMIT),
    };
    if (options.stack) body.stack = truncate(options.stack, STACK_LIMIT);
    if (options.metadata) body.metadata = options.metadata;

    // Belt and braces: JSON escaping can expand a stack full of newlines, and
    // metadata is caller-supplied. Context is the first thing to go, because
    // the level and the message are the report.
    let payload = JSON.stringify(body);
    // Byte length, not `.length`. A JS string reports UTF-16 code units, so
    // any non-ASCII content -- an accented prompt, an emoji, a CJK error
    // message -- occupies more bytes on the wire than characters in memory,
    // and a payload that measures under the cap here can still exceed it as
    // transmitted. TextEncoder measures what actually gets sent.
    if (new TextEncoder().encode(payload).length > MAX_LOG_BODY_BYTES) {
      delete body.metadata;
      payload = JSON.stringify(body);
    }

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (options.correlationId) headers['X-Correlation-ID'] = options.correlationId;

    await fetch(`${API_BASE_URL}${API_ROUTES.LOG}`, {
      method: 'POST',
      headers,
      body: payload,
      // The crash may be followed immediately by a reload or a navigation.
      keepalive: true,
    });
  } catch {
    // Intentionally empty. See the docstring: there is no useful recovery,
    // and re-raising would replace a caught render error with a network one.
  }
}

export default reportError;
