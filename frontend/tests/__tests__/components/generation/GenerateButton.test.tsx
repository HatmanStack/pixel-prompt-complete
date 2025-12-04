/**
 * Tests for GenerateButton component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GenerateButton } from '../../../../src/components/generation/GenerateButton';
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

describe('GenerateButton', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders with default label', () => {
    render(<GenerateButton onClick={vi.fn()} />);

    expect(screen.getByRole('button', { name: /generate images/i })).toBeInTheDocument();
  });

  it('renders with custom label', () => {
    render(<GenerateButton onClick={vi.fn()} label="Create Art" />);

    expect(screen.getByRole('button', { name: /create art/i })).toBeInTheDocument();
  });

  it('shows generating state', () => {
    render(<GenerateButton onClick={vi.fn()} isGenerating />);

    expect(screen.getByRole('button', { name: /generating/i })).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');
  });

  it('fires onClick when clicked', () => {
    const handleClick = vi.fn();
    render(<GenerateButton onClick={handleClick} />);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire onClick when generating', () => {
    const handleClick = vi.fn();
    render(<GenerateButton onClick={handleClick} isGenerating />);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).not.toHaveBeenCalled();
  });

  it('does not fire onClick when disabled', () => {
    const handleClick = vi.fn();
    render(<GenerateButton onClick={handleClick} disabled />);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).not.toHaveBeenCalled();
  });

  it('applies custom className', () => {
    render(<GenerateButton onClick={vi.fn()} className="custom-class" />);

    expect(screen.getByRole('button')).toHaveClass('custom-class');
  });

  it('has minimum height', () => {
    render(<GenerateButton onClick={vi.fn()} />);

    expect(screen.getByRole('button')).toHaveClass('min-h-14');
  });

  it('is full width', () => {
    render(<GenerateButton onClick={vi.fn()} />);

    expect(screen.getByRole('button')).toHaveClass('w-full');
  });
});
