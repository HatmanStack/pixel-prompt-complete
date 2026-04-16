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

  it('calls getDownloadUrl and opens URL on click', async () => {
    const { getDownloadUrl } = await import('../../../src/api/client');
    const mockGetDownloadUrl = vi.mocked(getDownloadUrl);
    mockGetDownloadUrl.mockResolvedValueOnce({
      url: 'https://s3.example.com/presigned-url',
      filename: 'gemini-1.png',
    });

    const openSpy = vi.fn();
    vi.stubGlobal('open', openSpy);

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
      expect(openSpy).toHaveBeenCalledWith('https://s3.example.com/presigned-url', '_blank');
    });
  });

  it('download click does not trigger onExpand', async () => {
    const { getDownloadUrl } = await import('../../../src/api/client');
    vi.mocked(getDownloadUrl).mockResolvedValueOnce({
      url: 'https://s3.example.com/presigned-url',
      filename: 'gemini-1.png',
    });
    vi.stubGlobal('open', vi.fn());

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
