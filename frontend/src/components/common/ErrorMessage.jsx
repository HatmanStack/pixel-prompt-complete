/**
 * ErrorMessage Component
 * Displays user-friendly error messages with appropriate actions
 */

import { getErrorMessage } from '../../utils/errorMessages';
import './ErrorMessage.css';

function ErrorMessage({ error, onRetry, onDismiss, showDetails = false }) {
  if (!error) return null;

  const errorInfo = getErrorMessage(error);

  return (
    <div className={`error-message error-message--${errorInfo.retryable ? 'retryable' : 'permanent'}`}>
      <div className="error-message__icon">
        {errorInfo.icon}
      </div>
      <div className="error-message__content">
        <h3 className="error-message__title">{errorInfo.title}</h3>
        <p className="error-message__text">{errorInfo.message}</p>
        {showDetails && errorInfo.originalError && (
          <details className="error-message__details">
            <summary>Technical Details</summary>
            <pre>{errorInfo.originalError}</pre>
          </details>
        )}
      </div>
      <div className="error-message__actions">
        {errorInfo.retryable && onRetry && (
          <button
            onClick={onRetry}
            className="error-message__button error-message__button--retry"
          >
            Try Again
          </button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="error-message__button error-message__button--dismiss"
          >
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}

export default ErrorMessage;
