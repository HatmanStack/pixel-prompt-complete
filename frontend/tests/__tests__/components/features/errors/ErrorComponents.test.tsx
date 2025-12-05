/**
 * Tests for ErrorBoundary and ErrorFallback components
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '../../../../../src/components/features/errors/ErrorBoundary';
import { ErrorFallback } from '../../../../../src/components/features/errors/ErrorFallback';
import { useUIStore } from '../../../../../src/stores/useUIStore';

// Mock Audio
vi.stubGlobal('Audio', vi.fn().mockImplementation(() => ({
  volume: 0.5,
  currentTime: 0,
  preload: '',
  src: '',
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn(),
})));

// Suppress console.error for error boundary tests
const originalError = console.error;
beforeEach(() => {
  console.error = vi.fn();
  useUIStore.setState({
    isMuted: false,
    volume: 0.5,
    soundsLoaded: true,
  });
});

afterEach(() => {
  console.error = originalError;
});

// Component that throws an error
const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>No error</div>;
};

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('catches errors and displays fallback UI', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('displays correlation ID', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Error ID:/)).toBeInTheDocument();
  });

  it('calls onReset callback on Try Again click', () => {
    const handleReset = vi.fn();

    render(
      <ErrorBoundary onReset={handleReset}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(handleReset).toHaveBeenCalledTimes(1);
  });

  it('calls onError callback', () => {
    const handleError = vi.fn();

    render(
      <ErrorBoundary onError={handleError}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(handleError).toHaveBeenCalled();
  });

  it('uses custom fallback component', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom fallback')).toBeInTheDocument();
  });

  it('uses custom fallback function', () => {
    render(
      <ErrorBoundary
        fallback={({ error }) => <div>Error: {error?.message}</div>}
      >
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Error: Test error')).toBeInTheDocument();
  });
});

describe('ErrorFallback', () => {
  const mockError = new Error('Test error message');
  const mockResetError = vi.fn();

  beforeEach(() => {
    mockResetError.mockClear();
  });

  it('renders error message', () => {
    render(
      <ErrorFallback error={mockError} resetError={mockResetError} />
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(
      screen.getByText(/We encountered an unexpected error/)
    ).toBeInTheDocument();
  });

  it('displays correlation ID when provided', () => {
    render(
      <ErrorFallback
        error={mockError}
        resetError={mockResetError}
        correlationId="err_123_abc"
      />
    );

    expect(screen.getByText('err_123_abc')).toBeInTheDocument();
  });

  it('renders Try Again button', () => {
    render(
      <ErrorFallback error={mockError} resetError={mockResetError} />
    );

    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('calls resetError when Try Again clicked', () => {
    render(
      <ErrorFallback error={mockError} resetError={mockResetError} />
    );

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(mockResetError).toHaveBeenCalledTimes(1);
  });

  it('renders Go Home button', () => {
    render(
      <ErrorFallback error={mockError} resetError={mockResetError} />
    );

    expect(screen.getByRole('button', { name: /go home/i })).toBeInTheDocument();
  });

  it('renders Refresh Page button', () => {
    render(
      <ErrorFallback error={mockError} resetError={mockResetError} />
    );

    expect(screen.getByRole('button', { name: /refresh page/i })).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <ErrorFallback
        error={mockError}
        resetError={mockResetError}
        className="custom-class"
      />
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
