/**
 * The boundary must render its fallback even when reporting fails.
 *
 * Separate from ErrorComponents.test.tsx because it mocks `@/api/log`, and
 * the tests there assert on the real reporter's `fetch` calls.
 *
 * `reportError` is contracted never to throw, and a rejecting `fetch` cannot
 * escape it. That makes "fetch rejected and the fallback still rendered" an
 * assertion that cannot fail, which is not coverage. What can fail — and what
 * actually matters — is whether the boundary survives that contract being
 * broken, because it is the last place in the UI that can still render
 * anything.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const reportError = vi.fn();
vi.mock('@/api/log', () => ({
  reportError: (...args: unknown[]) => reportError(...args),
}));

import { ErrorBoundary } from '../../../../src/components/errors/ErrorBoundary';

const Boom = () => {
  throw new Error('render exploded');
};

const originalError = console.error;
beforeEach(() => {
  console.error = vi.fn();
});
afterEach(() => {
  console.error = originalError;
  vi.clearAllMocks();
});

describe('ErrorBoundary resilience to a broken reporter', () => {
  it('renders its fallback when the reporter throws synchronously', () => {
    reportError.mockImplementation(() => {
      throw new TypeError('fetch is not a function');
    });

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('still shows the user a correlation id when the reporter throws', () => {
    reportError.mockImplementation(() => {
      throw new TypeError('fetch is not a function');
    });

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByText(/^err_/)).toBeInTheDocument();
  });

  it('reports with the level, message and component name', () => {
    reportError.mockImplementation(() => Promise.resolve());

    render(
      <ErrorBoundary componentName="Panel">
        <Boom />
      </ErrorBoundary>,
    );

    expect(reportError).toHaveBeenCalledTimes(1);
    const [level, message, options] = reportError.mock.calls[0];
    expect(level).toBe('ERROR');
    expect(message).toBe('render exploded');
    expect(options.metadata).toEqual({ component: 'Panel' });
    expect(options.correlationId).toMatch(/^err_/);
  });
});
