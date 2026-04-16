/**
 * Tests for PromptHistory component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Mock API client
const mockGetRecentPrompts = vi.fn();
const mockGetPromptHistory = vi.fn();
vi.mock('../../../src/api/client', () => ({
  getRecentPrompts: (...args: unknown[]) => mockGetRecentPrompts(...args),
  getPromptHistory: (...args: unknown[]) => mockGetPromptHistory(...args),
}));

// Mock auth store
let mockIsAuthenticated = false;
vi.mock('../../../src/stores/useAuthStore', () => ({
  useAuthStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ isAuthenticated: () => mockIsAuthenticated }),
    {
      getState: () => ({ isAuthenticated: () => mockIsAuthenticated }),
      setState: vi.fn(),
      subscribe: vi.fn(),
      destroy: vi.fn(),
    },
  ),
}));

// Mock app store
const mockSetPrompt = vi.fn();
vi.mock('../../../src/stores/useAppStore', () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({ prompt: '' }),
    {
      getState: () => ({ setPrompt: mockSetPrompt }),
      setState: vi.fn(),
      subscribe: vi.fn(),
      destroy: vi.fn(),
    },
  ),
}));

import { PromptHistory } from '../../../src/components/generation/PromptHistory';

describe('PromptHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsAuthenticated = false;
    mockGetRecentPrompts.mockResolvedValue({
      prompts: [
        { prompt: 'A sunset over mountains', sessionId: 's1', createdAt: Date.now() - 3600000 },
        { prompt: 'A cat in space', sessionId: 's2', createdAt: Date.now() - 7200000 },
      ],
      total: 2,
    });
    mockGetPromptHistory.mockResolvedValue({
      prompts: [
        { prompt: 'My saved prompt', sessionId: 's3', createdAt: Date.now() - 1800000 },
      ],
      total: 1,
    });
  });

  it('renders Recent tab for unauthenticated users without My History tab', async () => {
    mockIsAuthenticated = false;

    render(<PromptHistory />);

    // Expand the panel first
    fireEvent.click(screen.getByText('Prompt History'));

    expect(screen.getByText('Recent')).toBeDefined();
    expect(screen.queryByText('My History')).toBeNull();
  });

  it('renders both tabs for authenticated users', async () => {
    mockIsAuthenticated = true;

    render(<PromptHistory />);

    // Expand the panel
    fireEvent.click(screen.getByText('Prompt History'));

    expect(screen.getByText('Recent')).toBeDefined();
    expect(screen.getByText('My History')).toBeDefined();
  });

  it('fetches recent prompts on mount when expanded', async () => {
    render(<PromptHistory />);

    // Expand the panel
    fireEvent.click(screen.getByText('Prompt History'));

    await waitFor(() => {
      expect(mockGetRecentPrompts).toHaveBeenCalledWith(20);
    });
  });

  it('clicking a prompt calls setPrompt', async () => {
    render(<PromptHistory />);

    // Expand the panel
    fireEvent.click(screen.getByText('Prompt History'));

    await waitFor(() => {
      expect(screen.getByText('A sunset over mountains')).toBeDefined();
    });

    fireEvent.click(screen.getByText('A sunset over mountains'));

    expect(mockSetPrompt).toHaveBeenCalledWith('A sunset over mountains');
  });

  it('search filters history results', async () => {
    mockIsAuthenticated = true;

    render(<PromptHistory />);

    // Expand
    fireEvent.click(screen.getByText('Prompt History'));

    // Switch to My History tab
    fireEvent.click(screen.getByText('My History'));

    await waitFor(() => {
      expect(mockGetPromptHistory).toHaveBeenCalled();
    });

    // Type in search
    const searchInput = screen.getByPlaceholderText('Search prompts...');
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: 'landscape' } });
      // Wait for debounce
      await new Promise((r) => setTimeout(r, 350));
    });

    await waitFor(() => {
      expect(mockGetPromptHistory).toHaveBeenCalledWith(20, 'landscape');
    });
  });

  it('panel collapses on toggle', () => {
    render(<PromptHistory />);

    // Click to expand
    fireEvent.click(screen.getByText('Prompt History'));
    expect(screen.getByText('Recent')).toBeDefined();

    // Click to collapse
    fireEvent.click(screen.getByText('Prompt History'));

    // After collapse, tabs should not be visible
    expect(screen.queryByText('Recent')).toBeNull();
  });
});
