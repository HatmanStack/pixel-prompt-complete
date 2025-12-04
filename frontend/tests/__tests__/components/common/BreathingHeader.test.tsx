/**
 * Tests for BreathingHeader component
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BreathingHeader } from '../../../../src/components/common/BreathingHeader';

describe('BreathingHeader', () => {
  it('renders all characters of PIXEL PROMPT', () => {
    render(<BreathingHeader />);

    // Should have aria-label for accessibility
    expect(screen.getByRole('heading', { name: 'PIXEL PROMPT' })).toBeInTheDocument();
  });

  it('renders 12 character spans (including space)', () => {
    const { container } = render(<BreathingHeader />);

    // "PIXEL PROMPT" has 12 characters (including space)
    const spans = container.querySelectorAll('h1 > span');
    expect(spans.length).toBe(12);
  });

  it('applies staggered animation delays', () => {
    const { container } = render(<BreathingHeader />);

    const spans = container.querySelectorAll('h1 > span');
    const delays = Array.from(spans).map((span) =>
      (span as HTMLElement).style.animationDelay
    );

    // First character should have 0ms delay
    expect(delays[0]).toBe('0ms');

    // Last character should have longer delay
    const lastDelay = parseFloat(delays[delays.length - 1]);
    expect(lastDelay).toBeGreaterThan(0);
  });

  it('applies animation classes', () => {
    const { container } = render(<BreathingHeader />);

    const spans = container.querySelectorAll('h1 > span');
    spans.forEach((span) => {
      expect(span.className).toContain('animate-[letter-breathe');
      expect(span.className).toContain('motion-reduce:animate-none');
    });
  });

  it('passes custom className', () => {
    const { container } = render(<BreathingHeader className="custom-class" />);

    expect(container.querySelector('h1')).toHaveClass('custom-class');
  });

  it('uses font-display class for Sigmar font', () => {
    const { container } = render(<BreathingHeader />);

    expect(container.querySelector('h1')).toHaveClass('font-display');
  });

  it('is not selectable (user-select none)', () => {
    const { container } = render(<BreathingHeader />);

    expect(container.querySelector('h1')).toHaveClass('select-none');
  });

  it('has responsive text sizes', () => {
    const { container } = render(<BreathingHeader />);

    const h1 = container.querySelector('h1');
    expect(h1).toHaveClass('text-3xl');
    expect(h1).toHaveClass('sm:text-4xl');
    expect(h1).toHaveClass('md:text-5xl');
    expect(h1).toHaveClass('lg:text-6xl');
  });
});
