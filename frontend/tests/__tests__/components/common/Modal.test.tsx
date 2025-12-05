/**
 * Tests for Modal component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Modal } from '../../../../src/components/common/Modal';
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

describe('Modal', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
    document.body.style.overflow = '';
  });

  it('renders nothing when closed', () => {
    render(
      <Modal isOpen={false} onClose={vi.fn()}>
        Content
      </Modal>
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders when open', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()}>
        Modal Content
      </Modal>
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Modal Content')).toBeInTheDocument();
  });

  it('renders title when provided', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="Test Title">
        Content
      </Modal>
    );

    expect(screen.getByText('Test Title')).toBeInTheDocument();
  });

  it('renders close button', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()}>
        Content
      </Modal>
    );

    expect(screen.getByRole('button', { name: /close modal/i })).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const handleClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={handleClose}>
        Content
      </Modal>
    );

    fireEvent.click(screen.getByRole('button', { name: /close modal/i }));

    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when overlay clicked', () => {
    const handleClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={handleClose}>
        Content
      </Modal>
    );

    fireEvent.click(screen.getByRole('dialog'));

    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose when content clicked', () => {
    const handleClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={handleClose}>
        <div data-testid="content">Content</div>
      </Modal>
    );

    fireEvent.click(screen.getByTestId('content'));

    expect(handleClose).not.toHaveBeenCalled();
  });

  it('closes on Escape key', () => {
    const handleClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={handleClose}>
        Content
      </Modal>
    );

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('has aria-modal attribute', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()}>
        Content
      </Modal>
    );

    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
  });

  it('uses custom ariaLabel', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} ariaLabel="Custom label">
        Content
      </Modal>
    );

    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Custom label');
  });

  it('applies size styles', () => {
    const { rerender } = render(
      <Modal isOpen={true} onClose={vi.fn()} size="sm">
        Content
      </Modal>
    );

    expect(screen.getByRole('document')).toHaveClass('max-w-md');

    rerender(
      <Modal isOpen={true} onClose={vi.fn()} size="lg">
        Content
      </Modal>
    );

    expect(screen.getByRole('document')).toHaveClass('max-w-4xl');
  });

  it('applies custom className', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} className="custom-class">
        Content
      </Modal>
    );

    expect(screen.getByRole('document')).toHaveClass('custom-class');
  });
});
