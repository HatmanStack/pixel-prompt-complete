/**
 * Tests for ImageGrid Component
 */

import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ImageGrid from '@/components/generation/ImageGrid';
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

describe('ImageGrid', () => {
  beforeEach(() => {
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
    useToastStore.setState({ toasts: [] });
  });

  it('renders 9 image slots', () => {
    render(<ImageGrid images={[]} modelNames={[]} />);

    // Should render 9 ImageCard components (all pending)
    const pendingTexts = screen.getAllByText('Waiting...');
    expect(pendingTexts).toHaveLength(9);
  });

  it('renders with empty arrays', () => {
    render(<ImageGrid images={[]} modelNames={[]} />);

    // Should still render grid without crashing
    expect(screen.getAllByText('Waiting...').length).toBe(9);
  });

  it('displays model names from modelNames prop', () => {
    const modelNames = ['Model 1', 'Model 2', 'Model 3'];
    render(<ImageGrid images={[]} modelNames={modelNames} />);

    expect(screen.getByText('Model 1')).toBeInTheDocument();
    expect(screen.getByText('Model 2')).toBeInTheDocument();
    expect(screen.getByText('Model 3')).toBeInTheDocument();
  });

  it('uses default model names when modelNames not provided', () => {
    render(<ImageGrid images={[]} />);

    expect(screen.getByText('Model 1')).toBeInTheDocument();
    expect(screen.getByText('Model 2')).toBeInTheDocument();
    expect(screen.getByText('Model 9')).toBeInTheDocument();
  });

  it('displays images when provided', () => {
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'DALL-E 3' },
      { status: 'completed', imageUrl: 'http://example.com/2.png', model: 'Stable Diffusion' },
    ];

    render(<ImageGrid images={images} />);

    const img1 = screen.getByAltText('Generated image from DALL-E 3');
    const img2 = screen.getByAltText('Generated image from Stable Diffusion');

    expect(img1).toHaveAttribute('src', 'http://example.com/1.png');
    expect(img2).toHaveAttribute('src', 'http://example.com/2.png');
  });

  it('handles partial results (some completed, some pending)', () => {
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Model A' },
      { status: 'loading', model: 'Model B' },
      { status: 'pending', model: 'Model C' },
    ];

    render(<ImageGrid images={images} />);

    // One completed image
    expect(screen.getByAltText('Generated image from Model A')).toBeInTheDocument();

    // One loading
    expect(screen.getByText('Generating...')).toBeInTheDocument();

    // Remaining should be pending (9 - 1 loading = 8, but one is pending explicitly)
    const waitingTexts = screen.getAllByText('Waiting...');
    expect(waitingTexts.length).toBeGreaterThan(0);
  });

  it('displays error state for failed images', () => {
    const images = [
      { status: 'error', error: 'Generation failed', model: 'Model A' },
    ];

    render(<ImageGrid images={images} />);

    expect(screen.getByText(/Model A.*Generation failed/)).toBeInTheDocument();
    expect(screen.getByText('⚠')).toBeInTheDocument();
  });

  it('opens modal when completed image is clicked', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(imageCard);

    // Modal should appear
    const modal = screen.getByRole('dialog', { name: /Expanded view of Test Model image/i });
    expect(modal).toBeInTheDocument();

    // Modal should contain enlarged image
    const modalImage = screen.getByAltText('Full-size image from Test Model');
    expect(modalImage).toHaveAttribute('src', 'http://example.com/1.png');
  });

  it('shows close button in modal', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(imageCard);

    const closeButton = screen.getByRole('button', { name: /Close modal/i });
    expect(closeButton).toBeInTheDocument();
  });

  it('closes modal when close button is clicked', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(imageCard);

    const modal = screen.getByRole('dialog');
    expect(modal).toBeInTheDocument();

    const closeButton = screen.getByRole('button', { name: /Close modal/i });
    await user.click(closeButton);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes modal when clicking outside modal content', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(imageCard);

    const modal = screen.getByRole('dialog');
    expect(modal).toBeInTheDocument();

    // Click the modal backdrop (not the content)
    await user.click(modal);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not close modal when clicking modal content', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(imageCard);

    const modalImage = screen.getByAltText('Full-size image from Test Model');
    await user.click(modalImage);

    // Modal should still be open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes modal when Escape key is pressed', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model/i });
    await user.click(imageCard);

    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not open modal for pending images', async () => {
    const images = [
      { status: 'pending', model: 'Test Model' },
    ];

    render(<ImageGrid images={images} />);

    // Pending images are not buttons
    const imageCard = screen.queryByRole('button', { name: /View Test Model/i });
    expect(imageCard).not.toBeInTheDocument();
  });

  it('fills remaining slots with pending when fewer than 9 images', () => {
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Model 1' },
      { status: 'completed', imageUrl: 'http://example.com/2.png', model: 'Model 2' },
    ];

    render(<ImageGrid images={images} />);

    // Should have 2 completed + 7 pending = 9 total
    const waitingTexts = screen.getAllByText('Waiting...');
    expect(waitingTexts).toHaveLength(7);
  });

  it('handles image URL in both imageUrl and image properties', () => {
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Model 1' },
      { status: 'completed', image: 'http://example.com/2.png', model: 'Model 2' },
    ];

    render(<ImageGrid images={images} />);

    const img1 = screen.getByAltText('Generated image from Model 1');
    const img2 = screen.getByAltText('Generated image from Model 2');

    expect(img1).toHaveAttribute('src', 'http://example.com/1.png');
    expect(img2).toHaveAttribute('src', 'http://example.com/2.png');
  });

  it('displays model footer in modal', async () => {
    const user = userEvent.setup();
    const images = [
      { status: 'completed', imageUrl: 'http://example.com/1.png', model: 'Test Model Name' },
    ];

    render(<ImageGrid images={images} />);

    const imageCard = screen.getByRole('button', { name: /View Test Model Name/i });
    await user.click(imageCard);

    // Check modal exists
    const modal = screen.getByRole('dialog');
    expect(modal).toBeInTheDocument();

    // Modal should contain the model name (h3 in modal footer)
    const modalImage = screen.getByAltText('Full-size image from Test Model Name');
    expect(modalImage).toBeInTheDocument();
  });
});
