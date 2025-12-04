/**
 * React Error Boundary Component
 * Catches errors in child components and displays fallback UI
 */

import { Component, type ReactNode, type ErrorInfo } from 'react';
import { Button } from '@/components/common/Button';

interface ErrorBoundaryProps {
  children: ReactNode;
  componentName?: string;
  fallback?: ReactNode | ((props: ErrorBoundaryRenderProps) => ReactNode);
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  onReset?: () => void;
  resetKeys?: unknown[];
}

interface ErrorBoundaryRenderProps {
  error: Error | null;
  errorInfo: ErrorInfo | null;
  correlationId: string | null;
  resetError: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  correlationId: string | null;
}

/**
 * Generate a simple correlation ID
 */
function generateCorrelationId(): string {
  return `err_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const correlationId = generateCorrelationId();

    // Log error (in production this would go to CloudWatch/etc)
    console.error('Error Boundary caught:', {
      correlationId,
      component: this.props.componentName || 'Unknown',
      error: error.message,
      stack: errorInfo.componentStack,
    });

    this.setState({
      error,
      errorInfo,
      correlationId,
    });

    this.props.onError?.(error, errorInfo);
  }

  resetError = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
    });

    this.props.onReset?.();
  };

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (this.props.resetKeys && this.state.hasError) {
      const hasChanged = this.props.resetKeys.some(
        (key, index) => key !== prevProps.resetKeys?.[index]
      );

      if (hasChanged) {
        this.resetError();
      }
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
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
        <div className="p-6 m-4 border-2 border-error rounded-lg bg-error/10">
          <h2 className="text-xl font-display text-error mb-2">
            Something went wrong
          </h2>
          <p className="text-text-secondary mb-4">
            We're sorry, but an error occurred while rendering this section.
          </p>
          {this.state.correlationId && (
            <p className="text-sm text-text-secondary mb-4">
              Error ID:{' '}
              <code className="px-2 py-0.5 bg-primary rounded text-xs">
                {this.state.correlationId}
              </code>
            </p>
          )}
          <div className="flex gap-3">
            <Button variant="primary" onClick={this.resetError}>
              Try Again
            </Button>
            <Button
              variant="secondary"
              onClick={() => window.location.reload()}
            >
              Refresh Page
            </Button>
          </div>
          {import.meta.env.DEV && this.state.error && (
            <details className="mt-4">
              <summary className="cursor-pointer text-text-secondary text-sm">
                Error Details (Development Only)
              </summary>
              <pre className="mt-2 p-3 bg-primary rounded text-xs overflow-auto max-h-48">
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
