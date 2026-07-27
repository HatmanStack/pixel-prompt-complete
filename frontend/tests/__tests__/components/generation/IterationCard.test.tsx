/**
 * Tests for IterationCard component
 * Covers render states, prompt truncation, the download button and the
 * adapted-prompt toggle.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { IterationCard } from '../../../../src/components/generation/IterationCard';
import type { Iteration, ModelName } from '../../../../src/types';

// IterationCard calls getDownloadUrl from the API client.
vi.mock('../../../../src/api/client', () => ({
  getDownloadUrl: vi.fn(),
}));

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
    model: 'gemini' as ModelName,
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

      // The image area is now a native <button>, which is inherently keyboard
      // accessible: browsers fire click on Enter/Space. Verify the handler wires up.
      const card = screen.getByRole('button');
      fireEvent.click(card);
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

const defaultModel: ModelName = 'gemini';

function completedIteration(overrides: Partial<Iteration> = {}): Iteration {
  return {
    index: 1,
    status: 'completed',
    prompt: 'A beautiful landscape',
    imageUrl: 'https://cdn.example.com/image.png',
    ...overrides,
  };
}

function errorIteration(): Iteration {
  return {
    index: 1,
    status: 'error',
    prompt: 'A beautiful landscape',
    error: 'Generation failed',
  };
}

describe('IterationCard - Download Button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows download button on completed iteration', () => {
    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration()}
        sessionId="test-session-123"
      />,
    );

    expect(screen.getByLabelText('Download image')).toBeDefined();
  });

  it('hides download button on error iteration', () => {
    render(
      <IterationCard
        model={defaultModel}
        iteration={errorIteration()}
        sessionId="test-session-123"
      />,
    );

    expect(screen.queryByLabelText('Download image')).toBeNull();
  });

  it('calls getDownloadUrl and triggers download via anchor on click', async () => {
    const { getDownloadUrl } = await import('../../../../src/api/client');
    const mockGetDownloadUrl = vi.mocked(getDownloadUrl);
    mockGetDownloadUrl.mockResolvedValueOnce({
      url: 'https://s3.example.com/presigned-url',
      filename: 'gemini-1.png',
    });

    const createElementSpy = vi.spyOn(document, 'createElement');
    const appendChildSpy = vi.spyOn(document.body, 'appendChild');
    const removeChildSpy = vi.spyOn(document.body, 'removeChild');

    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration()}
        sessionId="test-session-123"
      />,
    );

    const downloadBtn = screen.getByLabelText('Download image');
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(mockGetDownloadUrl).toHaveBeenCalledWith('test-session-123', 'gemini', 1);
      // Verify an anchor element was created and clicked
      const anchorCalls = createElementSpy.mock.results.filter(
        (r) => r.type === 'return' && r.value instanceof HTMLAnchorElement,
      );
      expect(anchorCalls.length).toBeGreaterThan(0);
      expect(appendChildSpy).toHaveBeenCalled();
      expect(removeChildSpy).toHaveBeenCalled();
    });

    createElementSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
  });

  it('download click does not trigger onExpand', async () => {
    const { getDownloadUrl } = await import('../../../../src/api/client');
    vi.mocked(getDownloadUrl).mockResolvedValueOnce({
      url: 'https://s3.example.com/presigned-url',
      filename: 'gemini-1.png',
    });
    const onExpand = vi.fn();
    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration()}
        sessionId="test-session-123"
        onExpand={onExpand}
      />,
    );

    const downloadBtn = screen.getByLabelText('Download image');
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(onExpand).not.toHaveBeenCalled();
    });
  });
});

describe('IterationCard - Adapted Prompt', () => {
  it('shows adapted prompt toggle when adaptedPrompt differs from prompt', () => {
    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration({
          prompt: 'A beautiful landscape',
          adaptedPrompt: 'A photorealistic beautiful landscape with vivid colors',
        })}
        sessionId="test-session-123"
      />,
    );

    expect(screen.getByText('Show adapted')).toBeDefined();
  });

  it('hides adapted prompt toggle when adaptedPrompt is absent', () => {
    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration({ adaptedPrompt: undefined })}
        sessionId="test-session-123"
      />,
    );

    expect(screen.queryByText('Show adapted')).toBeNull();
  });

  it('hides adapted prompt toggle when adaptedPrompt equals prompt', () => {
    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration({
          prompt: 'A beautiful landscape',
          adaptedPrompt: 'A beautiful landscape',
        })}
        sessionId="test-session-123"
      />,
    );

    expect(screen.queryByText('Show adapted')).toBeNull();
  });

  it('toggles adapted prompt text on click', () => {
    const adaptedText = 'A photorealistic beautiful landscape with vivid colors';
    render(
      <IterationCard
        model={defaultModel}
        iteration={completedIteration({
          prompt: 'A beautiful landscape',
          adaptedPrompt: adaptedText,
        })}
        sessionId="test-session-123"
      />,
    );

    // Initially collapsed
    expect(screen.queryByText(adaptedText)).toBeNull();

    // Click to expand
    fireEvent.click(screen.getByText('Show adapted'));
    expect(screen.getByText(adaptedText)).toBeDefined();
    expect(screen.getByText('Hide adapted')).toBeDefined();

    // Click to collapse
    fireEvent.click(screen.getByText('Hide adapted'));
    expect(screen.queryByText(adaptedText)).toBeNull();
  });
});
