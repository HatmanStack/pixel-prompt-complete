/**
 * Tests for ImageCard Component
 */

import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../../context/ToastContext';
import ImageCard from '../../components/generation/ImageCard';

// Mock imageHelpers
vi.mock('../../utils/imageHelpers', () => ({
  downloadImage: vi.fn()
}));

// Helper to render with ToastProvider
const renderWithToast = (ui) => {
  return render(<ToastProvider>{ui}</ToastProvider>);
};

describe('ImageCard', () => {
  const mockOnExpand = vi.fn();

  beforeEach(() => {
    mockOnExpand.mockClear();
  });

  it('shows waiting state for pending status', () => {
    renderWithToast(<ImageCard status="pending" model="Test Model" />);
    expect(screen.getByText('Waiting...')).toBeInTheDocument();
  });

  it('shows generating state for loading status', () => {
    renderWithToast(<ImageCard status="loading" model="Test Model" />);
    expect(screen.getByText('Generating...')).toBeInTheDocument();
  });

  it('shows error state when status is error', () => {
    renderWithToast(<ImageCard status="error" model="Test Model" error="Generation failed" />);
    expect(screen.getByText('Generation failed')).toBeInTheDocument();
    expect(screen.getByText('⚠')).toBeInTheDocument();
  });

  it('shows default error message when error prop is missing', () => {
    renderWithToast(<ImageCard status="error" model="Test Model" />);
    expect(screen.getByText('Failed to load')).toBeInTheDocument();
  });

  it('displays image when status is completed', () => {
    const imageUrl = 'https://example.com/image.png';
    renderWithToast(<ImageCard status="completed" image={imageUrl} model="Test Model" />);

    const img = screen.getByAltText('Generated image from Test Model');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', imageUrl);
  });

  it('displays model name in footer', () => {
    renderWithToast(<ImageCard status="pending" model="DALL-E 3" />);
    expect(screen.getByText('DALL-E 3')).toBeInTheDocument();
  });

  it('shows checkmark badge when status is completed', () => {
    renderWithToast(<ImageCard status="completed" image="test.png" model="Test Model" />);
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('does not show checkmark badge when status is not completed', () => {
    renderWithToast(<ImageCard status="pending" model="Test Model" />);
    expect(screen.queryByText('✓')).not.toBeInTheDocument();
  });

  it('calls onExpand when completed image is clicked', async () => {
    const user = userEvent.setup();
    render(
      <ImageCard
        status="completed"
        image="test.png"
        model="Test Model"
        onExpand={mockOnExpand}
      />
    );

    // The card becomes a button when completed
    const card = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(card);

    expect(mockOnExpand).toHaveBeenCalled();
  });

  it('does not call onExpand when pending image is clicked', async () => {
    const user = userEvent.setup();
    render(
      <ImageCard
        status="pending"
        model="Test Model"
        onExpand={mockOnExpand}
      />
    );

    const card = screen.getByText('Test Model').parentElement.parentElement;
    await user.click(card);

    expect(mockOnExpand).not.toHaveBeenCalled();
  });

  it('has keyboard support for completed images (Enter key)', () => {
    render(
      <ImageCard
        status="completed"
        image="test.png"
        model="Test Model"
        onExpand={mockOnExpand}
      />
    );

    const card = screen.getByRole('button');
    fireEvent.keyDown(card, { key: 'Enter' });

    expect(mockOnExpand).toHaveBeenCalled();
  });

  it('has keyboard support for completed images (Space key)', () => {
    render(
      <ImageCard
        status="completed"
        image="test.png"
        model="Test Model"
        onExpand={mockOnExpand}
      />
    );

    const card = screen.getByRole('button');
    fireEvent.keyDown(card, { key: ' ' });

    expect(mockOnExpand).toHaveBeenCalled();
  });

  it('is not a button when status is pending', () => {
    renderWithToast(<ImageCard status="pending" model="Test Model" />);
    const button = screen.queryByRole('button');
    expect(button).not.toBeInTheDocument();
  });

  it('is not a button when status is error', () => {
    renderWithToast(<ImageCard status="error" model="Test Model" error="Failed" />);
    const button = screen.queryByRole('button');
    expect(button).not.toBeInTheDocument();
  });

  it('shows error state when image fails to load', () => {
    renderWithToast(<ImageCard status="completed" image="broken.png" model="Test Model" />);

    const img = screen.getByAltText('Generated image from Test Model');

    // Trigger image load error
    fireEvent.error(img);

    // Should show error UI
    expect(screen.getByText('Failed to load')).toBeInTheDocument();
  });

  it('has lazy loading attribute on image', () => {
    renderWithToast(<ImageCard status="completed" image="test.png" model="Test Model" />);
    const img = screen.getByAltText('Generated image from Test Model');
    expect(img).toHaveAttribute('loading', 'lazy');
  });

  it('handles missing model name gracefully', () => {
    renderWithToast(<ImageCard status="completed" image="test.png" />);
    // Should not crash, model name might be empty or undefined
    const card = screen.getByRole('button');
    expect(card).toBeInTheDocument();
  });

  it('does not crash when onExpand is not provided', async () => {
    const user = userEvent.setup();
    renderWithToast(<ImageCard status="completed" image="test.png" model="Test Model" />);

    const card = screen.getByRole('button');
    await user.click(card);

    // Should not throw error
    expect(true).toBe(true);
  });
});
