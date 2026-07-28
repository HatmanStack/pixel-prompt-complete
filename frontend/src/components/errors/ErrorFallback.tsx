/**
 * Error Fallback Component
 * Displays user-friendly error message with retry options
 */

import type { FC, ErrorInfo } from 'react';
import { Button } from '@/components/common/Button';

interface ErrorFallbackProps {
  error: Error | null;
  errorInfo?: ErrorInfo | null;
  correlationId?: string | null;
  resetError: () => void;
  className?: string;
}

export const ErrorFallback: FC<ErrorFallbackProps> = ({
  error,
  errorInfo,
  correlationId,
  resetError,
  className = '',
}) => {
  return (
    <div
      className={`
        flex items-center justify-center
        min-h-[400px] p-8
        bg-primary
        ${className}
      `}
    >
      <div className="max-w-md text-center">
        {/* Error icon */}
        <div className="text-6xl mb-4">⚠️</div>

        {/* Title */}
        <h2 className="text-2xl font-display text-error mb-3">Something went wrong</h2>

        {/* Message */}
        <p className="text-text-secondary mb-6">
          We encountered an unexpected error. Please try refreshing the page or contact support if
          the problem persists.
        </p>

        {/* Correlation ID */}
        {correlationId && (
          <p className="text-sm text-text-secondary mb-6">
            Error ID:{' '}
            <code className="px-2 py-0.5 bg-secondary rounded text-xs">{correlationId}</code>
          </p>
        )}

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button variant="primary" onClick={resetError}>
            Try Again
          </Button>
          <Button variant="secondary" onClick={() => (window.location.href = '/')}>
            Go Home
          </Button>
          <Button variant="ghost" onClick={() => window.location.reload()}>
            Refresh Page
          </Button>
        </div>

        {/* Dev details */}
        {import.meta.env.DEV && error && (
          <details className="mt-6 text-left">
            <summary className="cursor-pointer text-text-secondary text-sm hover:text-text transition-colors">
              Error Details (Development Only)
            </summary>
            <pre className="mt-2 p-3 bg-secondary rounded text-xs text-error overflow-auto max-h-48 text-left">
              {error.toString()}
              {'\n\n'}
              {errorInfo?.componentStack}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
};

export default ErrorFallback;
