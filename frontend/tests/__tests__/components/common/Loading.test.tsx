/**
 * Tests for Loading components
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoadingSpinner } from '../../../../src/components/common/LoadingSpinner';
import { LoadingSkeleton } from '../../../../src/components/common/LoadingSkeleton';

describe('LoadingSpinner', () => {
  it('renders with default message', () => {
    render(<LoadingSpinner />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders with custom message', () => {
    render(<LoadingSpinner message="Please wait..." />);

    expect(screen.getByText('Please wait...')).toBeInTheDocument();
  });

  it('renders without message when empty', () => {
    render(<LoadingSpinner message="" />);

    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
  });

  it('applies size classes', () => {
    const { container, rerender } = render(<LoadingSpinner size="sm" />);
    // Size classes are on the spinner div, not the outer container
    const spinner = container.querySelector('[aria-hidden="true"]');
    expect(spinner).toHaveClass('w-4', 'h-4');

    rerender(<LoadingSpinner size="lg" />);
    const largeSpinner = container.querySelector('[aria-hidden="true"]');
    expect(largeSpinner).toHaveClass('w-12', 'h-12');
  });

  it('applies custom className', () => {
    const { container } = render(<LoadingSpinner className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('has spin animation class', () => {
    const { container } = render(<LoadingSpinner />);
    // Custom spin animation with bounce effect
    const spinner = container.querySelector('[aria-hidden="true"]');
    expect(spinner?.className).toContain('animate-[spinBounce');
  });

  it('has motion-reduce support', () => {
    const { container } = render(<LoadingSpinner />);
    const spinner = container.querySelector('[aria-hidden="true"]');
    expect(spinner).toHaveClass('motion-reduce:animate-none');
  });
});

describe('LoadingSkeleton', () => {
  it('renders as hidden from screen readers', () => {
    const { container } = render(<LoadingSkeleton />);

    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');
  });

  it('applies rectangle shape by default', () => {
    const { container } = render(<LoadingSkeleton />);

    expect(container.firstChild).toHaveClass('rounded-md');
  });

  it('applies circle shape', () => {
    const { container } = render(<LoadingSkeleton shape="circle" />);

    expect(container.firstChild).toHaveClass('rounded-full');
  });

  it('applies text shape', () => {
    const { container } = render(<LoadingSkeleton shape="text" />);

    expect(container.firstChild).toHaveClass('rounded');
  });

  it('applies custom dimensions', () => {
    const { container } = render(
      <LoadingSkeleton width="200px" height="50px" />
    );

    const element = container.firstChild as HTMLElement;
    expect(element.style.width).toBe('200px');
    expect(element.style.height).toBe('50px');
  });

  it('applies numeric dimensions', () => {
    const { container } = render(
      <LoadingSkeleton width={100} height={30} />
    );

    const element = container.firstChild as HTMLElement;
    expect(element.style.width).toBe('100px');
    expect(element.style.height).toBe('30px');
  });

  it('has shimmer animation', () => {
    const { container } = render(<LoadingSkeleton />);
    // Custom shimmer animation instead of pulse
    expect((container.firstChild as HTMLElement).className).toContain('animate-[shimmer');
  });

  it('applies custom className', () => {
    const { container } = render(<LoadingSkeleton className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
