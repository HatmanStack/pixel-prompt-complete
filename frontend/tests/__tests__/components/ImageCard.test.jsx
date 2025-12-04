/**
 * Tests for ImageCard Component
 */

import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ImageCard from '@/components/generation/ImageCard';
import { useUIStore } from '@/stores/useUIStore';
import { useToastStore } from '@/stores/useToastStore';

// Mock imageHelpers
vi.mock('@/utils/imageHelpers', () => ({
  downloadImage: vi.fn()
}));

// Mock Audio
vi.stubGlobal('Audio', vi.fn().mockImplementation(() => ({
  volume: 0.5,
  currentTime: 0,
  preload: '',
  src: '',
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn(),
})));

describe('ImageCard', () => {
  const mockOnExpand = vi.fn();

  beforeEach(() => {
    mockOnExpand.mockClear();
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
    useToastStore.setState({ toasts: [] });
  });

  it('shows waiting state for pending status', () => {
    render(<ImageCard status="pending" model="Test Model" image={null} />);
    expect(screen.getByText('Waiting...')).toBeInTheDocument();
  });

  it('shows generating state for loading status', () => {
    render(<ImageCard status="loading" model="Test Model" image={null} />);
    expect(screen.getByText('Generating...')).toBeInTheDocument();
  });

  it('shows error state when status is error', () => {
    render(<ImageCard status="error" model="Test Model" image={null} error="Generation failed" />);
    expect(screen.getByText(/Test Model.*Generation failed/)).toBeInTheDocument();
    expect(screen.getByText('⚠')).toBeInTheDocument();
  });

  it('shows default error message when error prop is missing', () => {
    render(<ImageCard status="error" model="Test Model" image={null} />);
    expect(screen.getByText(/Test Model.*Failed to load/)).toBeInTheDocument();
  });

  it('displays image when status is completed', () => {
    const imageUrl = 'https://example.com/image.png';
    render(<ImageCard status="completed" image={imageUrl} model="Test Model" />);

    const img = screen.getByAltText('Generated image from Test Model');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', imageUrl);
  });

  it('displays model name in footer', () => {
    render(<ImageCard status="pending" model="DALL-E 3" image={null} />);
    expect(screen.getByText('DALL-E 3')).toBeInTheDocument();
  });

  it('shows checkmark badge when status is completed', () => {
    render(<ImageCard status="completed" image="test.png" model="Test Model" />);
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('does not show checkmark badge when status is not completed', () => {
    render(<ImageCard status="pending" model="Test Model" image={null} />);
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
        image={null}
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
    render(<ImageCard status="pending" model="Test Model" image={null} />);
    const button = screen.queryByRole('button');
    expect(button).not.toBeInTheDocument();
  });

  it('is not a button when status is error', () => {
    render(<ImageCard status="error" model="Test Model" image={null} error="Failed" />);
    const button = screen.queryByRole('button');
    expect(button).not.toBeInTheDocument();
  });

  it('shows error state when image fails to load', () => {
    render(<ImageCard status="completed" image="broken.png" model="Test Model" />);

    const img = screen.getByAltText('Generated image from Test Model');

    // Trigger image load error
    fireEvent.error(img);

    // Should show error UI
    expect(screen.getByText(/Test Model.*Failed to load/)).toBeInTheDocument();
  });

  it('has lazy loading attribute on image', () => {
    render(<ImageCard status="completed" image="test.png" model="Test Model" />);
    const img = screen.getByAltText('Generated image from Test Model');
    expect(img).toHaveAttribute('loading', 'lazy');
  });

  it('handles missing model name gracefully', () => {
    render(<ImageCard status="completed" image="test.png" model="" />);
    // Should not crash, model name might be empty or undefined
    const card = screen.getByRole('button');
    expect(card).toBeInTheDocument();
  });

  it('does not crash when onExpand is not provided', async () => {
    const user = userEvent.setup();
    render(<ImageCard status="completed" image="test.png" model="Test Model" />);

    const card = screen.getByRole('button');
    await user.click(card);

    // Should not throw error
    expect(true).toBe(true);
  });
});
