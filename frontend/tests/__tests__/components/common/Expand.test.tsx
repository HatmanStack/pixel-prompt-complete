/**
 * Tests for Expand component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Expand } from '../../../../src/components/common/Expand';
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

describe('Expand', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders title', () => {
    render(<Expand title="Section">Content</Expand>);

    expect(screen.getByText('Section')).toBeInTheDocument();
  });

  it('hides content by default', () => {
    render(<Expand title="Section">Hidden Content</Expand>);

    expect(screen.getByText('Hidden Content')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows content when defaultExpanded is true', () => {
    render(
      <Expand title="Section" defaultExpanded>
        Visible Content
      </Expand>
    );

    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles content on click', () => {
    render(<Expand title="Section">Content</Expand>);

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('calls onToggle callback', () => {
    const handleToggle = vi.fn();
    render(
      <Expand title="Section" onToggle={handleToggle}>
        Content
      </Expand>
    );

    fireEvent.click(screen.getByRole('button'));

    expect(handleToggle).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole('button'));

    expect(handleToggle).toHaveBeenCalledWith(false);
  });

  it('has proper ARIA attributes', () => {
    render(<Expand title="Section">Content</Expand>);

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-controls');
    expect(button).toHaveAttribute('aria-expanded');
  });

  it('content region has aria-hidden', () => {
    const { container } = render(<Expand title="Section">Content</Expand>);

    const content = container.querySelector('[aria-hidden]');
    expect(content).toHaveAttribute('aria-hidden', 'true');
  });

  it('applies custom className', () => {
    const { container } = render(
      <Expand title="Section" className="custom-class">
        Content
      </Expand>
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('has chevron icon that rotates', () => {
    const { container } = render(<Expand title="Section">Content</Expand>);

    const icon = container.querySelector('svg')?.parentElement;
    expect(icon).toHaveClass('rotate-0');

    fireEvent.click(screen.getByRole('button'));

    expect(icon).toHaveClass('rotate-180');
  });

  it('respects reduced motion', () => {
    const { container } = render(<Expand title="Section">Content</Expand>);

    const icon = container.querySelector('svg')?.parentElement;
    expect(icon).toHaveClass('motion-reduce:transition-none');
  });
});
