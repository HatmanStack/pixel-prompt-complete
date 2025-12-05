/**
 * Tests for KeyboardShortcutsHelp component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KeyboardShortcutsHelp } from '../../../../src/components/common/KeyboardShortcutsHelp';
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

describe('KeyboardShortcutsHelp', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders nothing when closed', () => {
    render(<KeyboardShortcutsHelp isOpen={false} onClose={vi.fn()} />);

    expect(screen.queryByText('Keyboard Shortcuts')).not.toBeInTheDocument();
  });

  it('renders when open', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    // Title appears as h2 with modal-title id
    expect(screen.getByRole('heading', { name: 'Keyboard Shortcuts' })).toBeInTheDocument();
  });

  it('renders all shortcut categories', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('Generation')).toBeInTheDocument();
    expect(screen.getByText('Downloads')).toBeInTheDocument();
    expect(screen.getByText('Navigation')).toBeInTheDocument();
    expect(screen.getByText('Utility')).toBeInTheDocument();
  });

  it('renders generation shortcuts', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('Generate Images')).toBeInTheDocument();
    expect(screen.getByText('Random Prompt')).toBeInTheDocument();
    expect(screen.getByText('Enhance Prompt')).toBeInTheDocument();
  });

  it('renders navigation shortcuts', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('Previous Image')).toBeInTheDocument();
    expect(screen.getByText('Next Image')).toBeInTheDocument();
    expect(screen.getByText('Close Modal')).toBeInTheDocument();
  });

  it('uses kbd elements for keys', () => {
    const { container } = render(
      <KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />
    );

    const kbdElements = container.querySelectorAll('kbd');
    expect(kbdElements.length).toBeGreaterThan(0);
  });

  it('shows Esc tip at bottom', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText(/Tip:/)).toBeInTheDocument();
    // Multiple Esc keys exist, just verify they're present
    expect(screen.getAllByText('Esc').length).toBeGreaterThan(0);
  });

  it('shows platform-specific modifier info', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    // Default platform in test env is not Mac
    expect(
      screen.getByText(/Windows\/Linux shortcuts use Ctrl/)
    ).toBeInTheDocument();
  });

  it('renders Enter key for generate shortcut', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('Enter')).toBeInTheDocument();
  });

  it('renders arrow keys for navigation', () => {
    render(<KeyboardShortcutsHelp isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText('←')).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();
  });
});
