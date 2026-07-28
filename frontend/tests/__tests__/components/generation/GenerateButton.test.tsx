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

  // Client retries no longer cover POST, so this guard is the only thing
  // between a double-click and a second four-model dispatch. It lives in the
  // component -- Button renders disabled={disabled || loading} and
  // GenerateButton always passes loading={isGenerating} -- so a call site
  // that forgets `disabled` still gets a button that cannot be clicked twice.
  it('is disabled while generating even when the call site omits disabled', () => {
    render(<GenerateButton onClick={vi.fn()} isGenerating />);

    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('issues one onClick when clicked twice in quick succession', () => {
    const handleClick = vi.fn();
    const { rerender } = render(<GenerateButton onClick={handleClick} />);

    fireEvent.click(screen.getByRole('button'));
    // The first click flips isGenerating, exactly as GenerationPanel does
    // before awaiting the request.
    rerender(<GenerateButton onClick={handleClick} isGenerating />);
    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).toHaveBeenCalledTimes(1);
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
