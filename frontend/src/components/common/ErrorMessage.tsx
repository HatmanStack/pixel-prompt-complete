/**
 * ErrorMessage Component
 * Displays inline error messages with optional retry
 */

import type { FC } from 'react';
import { Button } from './Button';

interface ErrorMessageProps {
  message: string;
  title?: string;
  onRetry?: () => void;
  onDismiss?: () => void;
  showDetails?: boolean;
  details?: string;
  retryable?: boolean;
  className?: string;
}

export const ErrorMessage: FC<ErrorMessageProps> = ({
  message,
  title = 'Error',
  onRetry,
  onDismiss,
  showDetails = false,
  details,
  retryable = true,
  className = '',
}) => {
  if (!message) return null;

  return (
    <div
      className={`
        p-4 rounded-lg
        border-l-4
        ${retryable ? 'border-warning bg-warning/10' : 'border-error bg-error/10'}
        ${className}
      `}
      role="alert"
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <span className="text-xl" aria-hidden="true">
          {retryable ? '⚠️' : '❌'}
        </span>

        {/* Content */}
        <div className="flex-1">
          <h3 className={`font-medium mb-1 ${retryable ? 'text-warning' : 'text-error'}`}>
            {title}
          </h3>
          <p className="text-text-secondary text-sm">{message}</p>

          {showDetails && details && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-text-secondary hover:text-text">
                Technical Details
              </summary>
              <pre className="mt-1 p-2 bg-primary rounded text-xs overflow-auto max-h-32">
                {details}
              </pre>
            </details>
          )}
        </div>
      </div>

      {/* Actions */}
      {(onRetry || onDismiss) && (
        <div className="flex gap-2 mt-3 ml-9">
          {retryable && onRetry && (
            <Button variant="primary" size="sm" onClick={onRetry}>
              Try Again
            </Button>
          )}
          {onDismiss && (
            <Button variant="ghost" size="sm" onClick={onDismiss}>
              Dismiss
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

export default ErrorMessage;
