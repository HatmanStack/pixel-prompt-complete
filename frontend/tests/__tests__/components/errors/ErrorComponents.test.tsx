/**
 * Tests for ErrorBoundary and ErrorFallback components
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ErrorBoundary } from '../../../../src/components/errors/ErrorBoundary';
import { ErrorFallback } from '../../../../src/components/errors/ErrorFallback';
import { useUIStore } from '../../../../src/stores/useUIStore';

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
  // ErrorBoundary reports to /log now. Stubbed so this suite does not make a
  // real request: a test suite that starts hitting the network is a slow,
  // flaky suite.
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200 }));
  useUIStore.setState({
    isMuted: false,
    volume: 0.5,
    soundsLoaded: true,
  });
});

afterEach(() => {
  console.error = originalError;
  vi.unstubAllGlobals();
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


describe('ErrorBoundary error reporting', () => {
  const posts = () =>
    (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter((call) =>
      String(call[0]).endsWith('/log'),
    );

  it('reports a caught error to /log exactly once', async () => {
    render(
      <ErrorBoundary componentName="TestArea">
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    await waitFor(() => expect(posts()).toHaveLength(1));

    const body = JSON.parse(posts()[0][1].body as string);
    expect(body.level).toBe('ERROR');
    expect(body.message).toBe('Test error');
    expect(body.metadata.component).toBe('TestArea');
  });

  it('sends the same correlation id the fallback shows the user', async () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    await waitFor(() => expect(posts()).toHaveLength(1));

    const headers = posts()[0][1].headers as Record<string, string>;
    expect(headers['X-Correlation-ID']).toMatch(/^err_/);
    expect(screen.getByText(headers['X-Correlation-ID'])).toBeInTheDocument();
  });

  it('still renders its fallback when the report fails', async () => {
    // The important one. A reporter that throws inside an error boundary
    // loses the original error -- the user sees nothing at all instead of
    // the fallback, which is strictly worse than not reporting.
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('offline'));

    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('does not report when no error is thrown', async () => {
    render(
      <ErrorBoundary>
        <div>Fine</div>
      </ErrorBoundary>
    );

    expect(posts()).toHaveLength(0);
  });

  it('keeps the console.error, which is free and useful in development', async () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(console.error).toHaveBeenCalled();
  });
});
