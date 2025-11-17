/**
 * React Error Boundary Component
 * Catches errors in child components and displays fallback UI
 */

import { Component } from 'react';
import { logError } from '../../../utils/logger';
import { generateCorrelationId } from '../../../utils/correlation';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
    };
  }

  static getDerivedStateFromError(error) {
    // Update state to trigger fallback UI
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error, errorInfo) {
    // Generate correlation ID for this error
    const correlationId = generateCorrelationId();

    // Log error to CloudWatch
    logError('React component error caught by ErrorBoundary', error, {
      correlationId,
      component: this.props.componentName || 'Unknown',
      componentStack: errorInfo.componentStack,
    });

    // Update state with error details
    this.setState({
      error,
      errorInfo,
      correlationId,
    });

    // Call custom onError callback if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  resetError = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
    });

    // Call custom onReset callback if provided
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  componentDidUpdate(prevProps) {
    // Reset error if resetKeys change
    if (this.props.resetKeys) {
      const hasChanged = this.props.resetKeys.some(
        (key, index) => key !== prevProps.resetKeys?.[index]
      );

      if (hasChanged && this.state.hasError) {
        this.resetError();
      }
    }
  }

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return typeof this.props.fallback === 'function'
          ? this.props.fallback({
              error: this.state.error,
              errorInfo: this.state.errorInfo,
              correlationId: this.state.correlationId,
              resetError: this.resetError,
            })
          : this.props.fallback;
      }

      // Default fallback UI
      return (
        <div style={{
          padding: '20px',
          margin: '20px',
          border: '2px solid #f44336',
          borderRadius: '8px',
          backgroundColor: '#ffebee',
        }}>
          <h2 style={{ color: '#c62828', margin: '0 0 10px 0' }}>
            ⚠️ Something went wrong
          </h2>
          <p style={{ color: '#666', margin: '0 0 15px 0' }}>
            We're sorry, but an error occurred while rendering this section.
          </p>
          {this.state.correlationId && (
            <p style={{ fontSize: '12px', color: '#999', marginBottom: '15px' }}>
              Error ID: {this.state.correlationId}
            </p>
          )}
          <button
            onClick={this.resetError}
            style={{
              padding: '10px 20px',
              marginRight: '10px',
              backgroundColor: '#2196f3',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Try Again
          </button>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              backgroundColor: '#757575',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Refresh Page
          </button>
          {import.meta.env.DEV && this.state.error && (
            <details style={{ marginTop: '20px' }}>
              <summary style={{ cursor: 'pointer', color: '#666' }}>
                Error Details (Development Only)
              </summary>
              <pre style={{
                marginTop: '10px',
                padding: '10px',
                backgroundColor: '#f5f5f5',
                borderRadius: '4px',
                overflow: 'auto',
                fontSize: '12px',
              }}>
                {this.state.error.toString()}
                {'\n\n'}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
