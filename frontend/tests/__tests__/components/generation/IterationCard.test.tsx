/**
 * Tests for IterationCard component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IterationCard } from '../../../../src/components/generation/IterationCard';
import type { Iteration, ModelName } from '../../../../src/types';

// Helper to create mock iteration
const createMockIteration = (overrides: Partial<Iteration> = {}): Iteration => ({
  index: 0,
  status: 'completed',
  prompt: 'test prompt for iteration',
  imageUrl: 'https://example.com/image.png',
  ...overrides,
});

describe('IterationCard', () => {
  const defaultProps = {
    model: 'flux' as ModelName,
    iteration: createMockIteration(),
    onExpand: vi.fn(),
  };

  describe('completed state', () => {
    it('renders image when completed', () => {
      render(<IterationCard {...defaultProps} />);

      const img = screen.getByRole('img');
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute('src', 'https://example.com/image.png');
    });

    it('shows status badge', () => {
      render(<IterationCard {...defaultProps} />);

      expect(screen.getByText('Done')).toBeInTheDocument();
    });

    it('shows iteration number and prompt', () => {
      render(<IterationCard {...defaultProps} />);

      expect(screen.getByText(/^#0:/)).toBeInTheDocument();
      expect(screen.getByText(/test prompt for iteration/)).toBeInTheDocument();
    });

    it('calls onExpand when clicked', () => {
      const onExpand = vi.fn();
      render(<IterationCard {...defaultProps} onExpand={onExpand} />);

      fireEvent.click(screen.getByRole('button'));
      expect(onExpand).toHaveBeenCalledTimes(1);
    });

    it('is keyboard accessible', () => {
      const onExpand = vi.fn();
      render(<IterationCard {...defaultProps} onExpand={onExpand} />);

      const card = screen.getByRole('button');
      fireEvent.keyDown(card, { key: 'Enter' });
      expect(onExpand).toHaveBeenCalledTimes(1);
    });
  });

  describe('loading state', () => {
    it('shows loading skeleton', () => {
      render(
        <IterationCard
          {...defaultProps}
          iteration={createMockIteration({ status: 'loading', imageUrl: undefined })}
        />
      );

      expect(screen.getByText('Generating...')).toBeInTheDocument();
    });

    it('is not clickable', () => {
      const onExpand = vi.fn();
      render(
        <IterationCard
          {...defaultProps}
          onExpand={onExpand}
          iteration={createMockIteration({ status: 'loading', imageUrl: undefined })}
        />
      );

      // Should not have button role when loading
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows error message', () => {
      render(
        <IterationCard
          {...defaultProps}
          iteration={createMockIteration({
            status: 'error',
            error: 'Generation failed',
            imageUrl: undefined,
          })}
        />
      );

      expect(screen.getByText('Error')).toBeInTheDocument();
      expect(screen.getByText('Generation failed')).toBeInTheDocument();
    });
  });

  describe('pending state', () => {
    it('shows placeholder', () => {
      render(
        <IterationCard
          {...defaultProps}
          iteration={createMockIteration({ status: 'pending', imageUrl: undefined })}
        />
      );

      expect(screen.getByText('Pending')).toBeInTheDocument();
    });
  });

  describe('prompt truncation', () => {
    it('truncates long prompts', () => {
      const longPrompt = 'This is a very long prompt that should be truncated because it exceeds the maximum character limit for display';
      render(
        <IterationCard
          {...defaultProps}
          iteration={createMockIteration({ prompt: longPrompt })}
        />
      );

      // Should show truncated version
      const promptText = screen.getByText(/^#0:/);
      expect(promptText.textContent?.length).toBeLessThan(longPrompt.length + 10);
    });
  });
});
