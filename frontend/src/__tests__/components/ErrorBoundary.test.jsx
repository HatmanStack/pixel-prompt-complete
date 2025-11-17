/**
 * Tests for ErrorBoundary component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import ErrorBoundary from '../../components/features/errors/ErrorBoundary';
import { logError } from '../../utils/logger';

// Mock the logger
vi.mock('../../utils/logger', () => ({
  logError: vi.fn(),
}));

// Mock correlation ID generation
vi.mock('../../utils/correlation', () => ({
  generateCorrelationId: () => 'test-correlation-id',
}));

// Component that throws an error
function ThrowError({ shouldThrow }) {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>No error</div>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // Suppress console.error for tests
    vi.spyOn(console, 'error').mockImplementation(() => {});
    logError.mockClear();
  });

  it('should render children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Test content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('should catch error and show fallback UI', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText('Try Again')).toBeInTheDocument();
    expect(screen.getByText('Refresh Page')).toBeInTheDocument();
  });

  it('should log error to CloudWatch', () => {
    render(
      <ErrorBoundary componentName="TestComponent">
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(logError).toHaveBeenCalledWith(
      'React component error caught by ErrorBoundary',
      expect.any(Error),
      expect.objectContaining({
        correlationId: 'test-correlation-id',
        component: 'TestComponent',
      })
    );
  });

  it('should display correlation ID', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Error ID: test-correlation-id/i)).toBeInTheDocument();
  });

  it('should reset error when Try Again clicked', async () => {
    const user = userEvent.setup();

    // Use a wrapper component to control the error state
    function Wrapper() {
      const [shouldThrow, setShouldThrow] = React.useState(true);

      return (
        <ErrorBoundary
          fallback={({ resetError }) => (
            <div>
              <p>Error occurred</p>
              <button onClick={() => { resetError(); setShouldThrow(false); }}>
                Try Again
              </button>
            </div>
          )}
        >
          <ThrowError shouldThrow={shouldThrow} />
        </ErrorBoundary>
      );
    }

    render(<Wrapper />);

    expect(screen.getByText('Error occurred')).toBeInTheDocument();

    const tryAgainButton = screen.getByText('Try Again');
    await user.click(tryAgainButton);

    expect(screen.getByText('No error')).toBeInTheDocument();
  });

  it('should call custom onError callback', () => {
    const onError = vi.fn();

    render(
      <ErrorBoundary onError={onError}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(onError).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        componentStack: expect.any(String),
      })
    );
  });

  it('should use custom fallback component', () => {
    const CustomFallback = () => <div>Custom error message</div>;

    render(
      <ErrorBoundary fallback={<CustomFallback />}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom error message')).toBeInTheDocument();
  });

  it('should use custom fallback function', () => {
    const CustomFallback = ({ error, resetError }) => (
      <div>
        <p>Error: {error.message}</p>
        <button onClick={resetError}>Reset</button>
      </div>
    );

    render(
      <ErrorBoundary fallback={CustomFallback}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Error: Test error/i)).toBeInTheDocument();
    expect(screen.getByText('Reset')).toBeInTheDocument();
  });

  it('should reset error when resetKeys change', () => {
    let shouldThrow = true;

    const { rerender } = render(
      <ErrorBoundary resetKeys={['key1']}>
        <ThrowError shouldThrow={shouldThrow} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();

    // Change resetKeys and make component not throw
    shouldThrow = false;

    rerender(
      <ErrorBoundary resetKeys={['key2']}>
        <ThrowError shouldThrow={shouldThrow} />
      </ErrorBoundary>
    );

    expect(screen.getByText('No error')).toBeInTheDocument();
  });

  it('should show error details in development mode', () => {
    // Set dev mode
    import.meta.env.DEV = true;

    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Error Details \(Development Only\)/i)).toBeInTheDocument();
  });
});
