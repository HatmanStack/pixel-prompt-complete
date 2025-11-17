/**
 * Error Fallback Component
 * Displays user-friendly error message when ErrorBoundary catches an error
 */

import './ErrorFallback.css';

function ErrorFallback({ error, errorInfo, correlationId, resetError }) {
  return (
    <div className="error-fallback">
      <div className="error-fallback-content">
        <div className="error-icon">⚠️</div>
        <h2 className="error-title">Something went wrong</h2>
        <p className="error-message">
          We encountered an unexpected error. Please try refreshing the page or contact support if the problem persists.
        </p>

        {correlationId && (
          <p className="error-id">
            Error ID: <code>{correlationId}</code>
          </p>
        )}

        <div className="error-actions">
          <button onClick={resetError} className="btn-primary">
            Try Again
          </button>
          <button onClick={() => window.location.href = '/'} className="btn-secondary">
            Go Home
          </button>
          <button onClick={() => window.location.reload()} className="btn-secondary">
            Refresh Page
          </button>
        </div>

        {import.meta.env.DEV && error && (
          <details className="error-details">
            <summary>Error Details (Development Only)</summary>
            <pre className="error-stack">
              {error.toString()}
              {'\n\n'}
              {errorInfo?.componentStack}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

export default ErrorFallback;
