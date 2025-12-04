/**
 * Tests for ErrorMessage component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorMessage } from '../../../../src/components/common/ErrorMessage';
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

describe('ErrorMessage', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders nothing when no message', () => {
    const { container } = render(<ErrorMessage message="" />);

    expect(container.firstChild).toBeNull();
  });

  it('renders message', () => {
    render(<ErrorMessage message="Something went wrong" />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('renders default title', () => {
    render(<ErrorMessage message="Something went wrong" />);

    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('renders custom title', () => {
    render(<ErrorMessage message="Failed to load" title="Loading Error" />);

    expect(screen.getByText('Loading Error')).toBeInTheDocument();
  });

  it('renders retry button when retryable and onRetry provided', () => {
    render(
      <ErrorMessage
        message="Try again"
        onRetry={vi.fn()}
        retryable={true}
      />
    );

    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('does not render retry when not retryable', () => {
    render(
      <ErrorMessage
        message="Permanent error"
        onRetry={vi.fn()}
        retryable={false}
      />
    );

    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  });

  it('calls onRetry when retry button clicked', () => {
    const handleRetry = vi.fn();
    render(<ErrorMessage message="Error" onRetry={handleRetry} />);

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it('renders dismiss button when onDismiss provided', () => {
    render(<ErrorMessage message="Dismissable" onDismiss={vi.fn()} />);

    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  it('calls onDismiss when dismiss button clicked', () => {
    const handleDismiss = vi.fn();
    render(<ErrorMessage message="Dismiss me" onDismiss={handleDismiss} />);

    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));

    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('shows details when showDetails is true', () => {
    render(
      <ErrorMessage
        message="Error occurred"
        showDetails={true}
        details="Stack trace here"
      />
    );

    expect(screen.getByText('Technical Details')).toBeInTheDocument();
    expect(screen.getByText('Stack trace here')).toBeInTheDocument();
  });

  it('has alert role', () => {
    render(<ErrorMessage message="Alert message" />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('applies retryable styling', () => {
    const { container } = render(
      <ErrorMessage message="Retryable" retryable={true} />
    );

    expect(container.firstChild).toHaveClass('border-warning');
  });

  it('applies permanent styling', () => {
    const { container } = render(
      <ErrorMessage message="Permanent" retryable={false} />
    );

    expect(container.firstChild).toHaveClass('border-error');
  });

  it('applies custom className', () => {
    const { container } = render(
      <ErrorMessage message="Custom" className="custom-class" />
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
