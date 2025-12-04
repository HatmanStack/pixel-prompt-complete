/**
 * Tests for Toast and ToastContainer components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { Toast } from '../../../../src/components/common/Toast';
import { ToastContainer } from '../../../../src/components/common/ToastContainer';
import { ToastProvider, useToast } from '../../../../src/context/ToastContext';
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

// Mock createPortal
vi.mock('react-dom', async () => {
  const actual = await vi.importActual('react-dom');
  return {
    ...actual,
    createPortal: (node: React.ReactNode) => node,
  };
});

describe('Toast', () => {
  it('renders message', () => {
    render(
      <Toast id={1} message="Test message" type="info" onDismiss={vi.fn()} />
    );

    expect(screen.getByText('Test message')).toBeInTheDocument();
  });

  it('renders success icon', () => {
    render(
      <Toast id={1} message="Success" type="success" onDismiss={vi.fn()} />
    );

    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('renders error icon', () => {
    render(
      <Toast id={1} message="Error" type="error" onDismiss={vi.fn()} />
    );

    expect(screen.getByText('✕')).toBeInTheDocument();
  });

  it('renders warning icon', () => {
    render(
      <Toast id={1} message="Warning" type="warning" onDismiss={vi.fn()} />
    );

    expect(screen.getByText('⚠')).toBeInTheDocument();
  });

  it('renders info icon', () => {
    render(
      <Toast id={1} message="Info" type="info" onDismiss={vi.fn()} />
    );

    expect(screen.getByText('ℹ')).toBeInTheDocument();
  });

  it('calls onDismiss when close button clicked', () => {
    const handleDismiss = vi.fn();
    render(
      <Toast id={42} message="Test" type="info" onDismiss={handleDismiss} />
    );

    fireEvent.click(screen.getByRole('button', { name: /close/i }));

    expect(handleDismiss).toHaveBeenCalledWith(42);
  });

  it('applies type-specific styles', () => {
    const { container } = render(
      <Toast id={1} message="Error" type="error" onDismiss={vi.fn()} />
    );

    expect(container.firstChild).toHaveClass('bg-error');
  });
});

describe('ToastContainer', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders nothing when no toasts', () => {
    render(
      <ToastProvider>
        <ToastContainer />
      </ToastProvider>
    );

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('renders toasts from context', () => {
    // Component that adds a toast
    const TestComponent = () => {
      const { success } = useToast();

      return (
        <button onClick={() => success('Test toast')}>Add Toast</button>
      );
    };

    render(
      <ToastProvider>
        <TestComponent />
        <ToastContainer />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Add Toast'));

    expect(screen.getByText('Test toast')).toBeInTheDocument();
  });

  it('removes toast when dismissed', () => {
    const TestComponent = () => {
      const { info } = useToast();

      return (
        <button onClick={() => info('Dismissable toast', 0)}>Add Toast</button>
      );
    };

    render(
      <ToastProvider>
        <TestComponent />
        <ToastContainer />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Add Toast'));
    expect(screen.getByText('Dismissable toast')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Dismissable toast')).not.toBeInTheDocument();
  });

  it('has proper ARIA attributes', () => {
    const TestComponent = () => {
      const { info } = useToast();

      return (
        <button onClick={() => info('Accessible toast', 0)}>Add Toast</button>
      );
    };

    render(
      <ToastProvider>
        <TestComponent />
        <ToastContainer />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Add Toast'));

    const container = screen.getByRole('status').parentElement?.parentElement;
    expect(container).toHaveAttribute('aria-live', 'polite');
  });

  it('auto-dismisses after duration', async () => {
    vi.useFakeTimers();

    const TestComponent = () => {
      const { info } = useToast();

      return (
        <button onClick={() => info('Auto dismiss', 1000)}>Add Toast</button>
      );
    };

    render(
      <ToastProvider>
        <TestComponent />
        <ToastContainer />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Add Toast'));
    expect(screen.getByText('Auto dismiss')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.queryByText('Auto dismiss')).not.toBeInTheDocument();

    vi.useRealTimers();
  });
});
