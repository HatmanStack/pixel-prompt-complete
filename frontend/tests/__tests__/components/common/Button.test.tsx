/**
 * Tests for Button component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '../../../../src/components/common/Button';
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

describe('Button', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders children', () => {
    render(<Button>Click me</Button>);

    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('fires onClick when clicked', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire onClick when disabled', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick} disabled>Click me</Button>);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).not.toHaveBeenCalled();
  });

  it('does not fire onClick when loading', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick} loading>Click me</Button>);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).not.toHaveBeenCalled();
  });

  it('shows loading spinner when loading', () => {
    render(<Button loading>Click me</Button>);

    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');
    // Spinner SVG should be present
    expect(screen.getByRole('button').querySelector('svg')).toBeInTheDocument();
  });

  it('applies variant styles', () => {
    const { rerender } = render(<Button variant="primary">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-accent');

    rerender(<Button variant="danger">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-error');

    rerender(<Button variant="ghost">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-transparent');
  });

  it('applies size styles', () => {
    const { rerender } = render(<Button size="sm">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('text-sm');

    rerender(<Button size="lg">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('text-lg');
  });

  it('applies fullWidth class', () => {
    render(<Button fullWidth>Click</Button>);

    expect(screen.getByRole('button')).toHaveClass('w-full');
  });

  it('passes custom className', () => {
    render(<Button className="custom-class">Click</Button>);

    expect(screen.getByRole('button')).toHaveClass('custom-class');
  });

  it('has correct button type', () => {
    const { rerender } = render(<Button>Click</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');

    rerender(<Button type="submit">Click</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit');
  });

  it('applies disabled state correctly', () => {
    render(<Button disabled>Click</Button>);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(button).toHaveClass('disabled:cursor-not-allowed');
  });
});
