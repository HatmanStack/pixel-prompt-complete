/**
 * Tests for IterationCard component
 * Covers download button, adapted prompt display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { IterationCard } from '../../../src/components/generation/IterationCard';
import type { Iteration, ModelName } from '../../../src/types/api';

// Mock the API client
vi.mock('../../../src/api/client', () => ({
  getDownloadUrl: vi.fn(),
}));

// Mock the app store
vi.mock('../../../src/stores/useAppStore', () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ currentSession: { sessionId: 'test-session-123' } }),
    {
      getState: () => ({ currentSession: { sessionId: 'test-session-123' } }),
      setState: vi.fn(),
      subscribe: vi.fn(),
      destroy: vi.fn(),
    },
  ),
}));

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
    const { getDownloadUrl } = await import('../../../src/api/client');
    const mockGetDownloadUrl = vi.mocked(getDownloadUrl);
    mockGetDownloadUrl.mockResolvedValueOnce({
      url: 'https://s3.example.com/presigned-url',
      filename: 'gemini-1.png',
    });

    const clickSpy = vi.fn();
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
    const { getDownloadUrl } = await import('../../../src/api/client');
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
