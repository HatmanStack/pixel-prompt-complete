/**
 * Tests for SoundToggle component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SoundToggle } from '../../../../src/components/common/SoundToggle';
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

describe('SoundToggle', () => {
  beforeEach(() => {
    // Reset store state
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders unmute button when not muted', () => {
    render(<SoundToggle />);

    const button = screen.getByRole('button', { name: /mute sounds/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });

  it('renders mute button when muted', () => {
    useUIStore.setState({ isMuted: true });
    render(<SoundToggle />);

    const button = screen.getByRole('button', { name: /unmute sounds/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('toggles mute state on click', () => {
    render(<SoundToggle />);

    const button = screen.getByRole('button');

    expect(useUIStore.getState().isMuted).toBe(false);

    fireEvent.click(button);

    expect(useUIStore.getState().isMuted).toBe(true);
  });

  it('passes custom className', () => {
    render(<SoundToggle className="custom-class" />);

    const button = screen.getByRole('button');
    expect(button).toHaveClass('custom-class');
  });

  it('has accessible label', () => {
    render(<SoundToggle />);

    const button = screen.getByRole('button');
    expect(button).toHaveAccessibleName(/mute sounds/i);
  });

  it('uses aria-pressed for toggle state', () => {
    const { rerender } = render(<SoundToggle />);

    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false');

    act(() => {
      useUIStore.setState({ isMuted: true });
    });
    rerender(<SoundToggle />);

    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true');
  });
});
