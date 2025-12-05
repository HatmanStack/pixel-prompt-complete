/**
 * Tests for Header component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Header } from '../../../../src/components/common/Header';
import { useAppStore } from '../../../../src/stores/useAppStore';
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

describe('Header', () => {
  beforeEach(() => {
    // Reset stores
    useAppStore.setState({
      currentView: 'generation',
    });
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders breathing header title', () => {
    render(<Header />);

    expect(screen.getByRole('heading', { name: 'PIXEL PROMPT' })).toBeInTheDocument();
  });

  it('renders tagline', () => {
    render(<Header />);

    expect(screen.getByText(/text-to-image variety pack/i)).toBeInTheDocument();
  });

  it('renders navigation buttons', () => {
    render(<Header />);

    expect(screen.getByRole('button', { name: /generate/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /gallery/i })).toBeInTheDocument();
  });

  it('renders sound toggle', () => {
    render(<Header />);

    expect(screen.getByRole('button', { name: /mute sounds/i })).toBeInTheDocument();
  });

  it('highlights active navigation button', () => {
    render(<Header />);

    const generateBtn = screen.getByRole('button', { name: /generate/i });
    const galleryBtn = screen.getByRole('button', { name: /gallery/i });

    expect(generateBtn).toHaveAttribute('aria-current', 'page');
    expect(galleryBtn).not.toHaveAttribute('aria-current');
  });

  it('switches view on navigation click', () => {
    render(<Header />);

    const galleryBtn = screen.getByRole('button', { name: /gallery/i });
    fireEvent.click(galleryBtn);

    expect(useAppStore.getState().currentView).toBe('gallery');
  });

  it('updates aria-current when view changes', () => {
    const { rerender } = render(<Header />);

    // Click gallery
    const galleryBtn = screen.getByRole('button', { name: /gallery/i });
    fireEvent.click(galleryBtn);

    // Rerender to reflect state change
    rerender(<Header />);

    expect(galleryBtn).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: /generate/i })).not.toHaveAttribute(
      'aria-current'
    );
  });

  it('passes custom className', () => {
    const { container } = render(<Header className="custom-class" />);

    expect(container.querySelector('header')).toHaveClass('custom-class');
  });

  it('has proper navigation role', () => {
    render(<Header />);

    expect(screen.getByRole('navigation', { name: /main/i })).toBeInTheDocument();
  });
});
