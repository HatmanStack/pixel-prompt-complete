/**
 * Tests for PromptEnhancer Component
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PromptEnhancer from '@/components/generation/PromptEnhancer';
import * as apiClient from '@/api/client';
import { useAppStore } from '@/stores/useAppStore';
import { useUIStore } from '@/stores/useUIStore';
import { useToastStore } from '@/stores/useToastStore';

// Mock the API client
vi.mock('@/api/client');

// Mock Audio
vi.stubGlobal('Audio', vi.fn().mockImplementation(() => ({
  volume: 0.5,
  currentTime: 0,
  preload: '',
  src: '',
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn(),
})));

describe('PromptEnhancer', () => {
  beforeEach(() => {
    // Reset stores before each test
    useAppStore.setState({ prompt: '' });
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
    useToastStore.setState({ toasts: [] });
    vi.clearAllMocks();
  });

  it('renders enhance button with icon', () => {
    act(() => {
      useAppStore.setState({ prompt: 'test' });
    });

    render(<PromptEnhancer />);
    expect(screen.getByText('Enhance Prompt')).toBeInTheDocument();
    expect(screen.getByText('✨')).toBeInTheDocument();
  });

  it('button is disabled when no prompt is entered', () => {
    render(<PromptEnhancer />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).toBeDisabled();
  });

  it('button is disabled when prompt is only whitespace', () => {
    act(() => {
      useAppStore.setState({ prompt: '   ' });
    });

    render(<PromptEnhancer />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).toBeDisabled();
  });

  it('button is enabled when valid prompt is entered', () => {
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    render(<PromptEnhancer />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).not.toBeDisabled();
  });

  it('button is disabled when disabled prop is true', () => {
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    render(<PromptEnhancer disabled={true} />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).toBeDisabled();
  });

  it('shows loading state when enhancing', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    // Mock API call that takes time
    apiClient.enhancePrompt.mockImplementation(() => new Promise(() => {}));

    render(<PromptEnhancer />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(screen.getByText('Enhancing...')).toBeInTheDocument();
  });

  it('calls API and shows enhanced result on success', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Enhanced short version',
      long_prompt: 'Enhanced long version with more details'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText('Enhanced Prompt')).toBeInTheDocument();
    });

    expect(apiClient.enhancePrompt).toHaveBeenCalledWith('cat');
    expect(screen.getByText('Original:')).toBeInTheDocument();
    expect(screen.getByText('cat')).toBeInTheDocument();
    expect(screen.getByText('Enhanced:')).toBeInTheDocument();
  });

  it('shows short/long toggle buttons when enhanced', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Short version',
      long_prompt: 'Long version'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Short')).toBeInTheDocument();
      expect(screen.getByText('Long')).toBeInTheDocument();
    });
  });

  it('toggles between short and long enhanced prompts', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Short version',
      long_prompt: 'Long version with details'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Short version')).toBeInTheDocument();
    });

    const longButton = screen.getByRole('button', { name: 'Long' });
    await user.click(longButton);

    expect(screen.getByText('Long version with details')).toBeInTheDocument();
    expect(screen.queryByText('Short version')).not.toBeInTheDocument();
  });

  it('shows "Use This" and "Discard" buttons when enhanced', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Short',
      long_prompt: 'Long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Use This')).toBeInTheDocument();
      expect(screen.getByText('Discard')).toBeInTheDocument();
    });
  });

  it('updates store with short version when "Use This" is clicked', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Enhanced short',
      long_prompt: 'Enhanced long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Use This')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Use This'));

    expect(useAppStore.getState().prompt).toBe('Enhanced short');
  });

  it('updates store with long version when long is selected', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Enhanced short',
      long_prompt: 'Enhanced long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Long')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Long' }));
    await user.click(screen.getByText('Use This'));

    expect(useAppStore.getState().prompt).toBe('Enhanced long');
  });

  it('clears enhanced result when "Discard" is clicked', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    const mockResponse = {
      short_prompt: 'Enhanced short',
      long_prompt: 'Enhanced long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Use This')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Discard'));

    // Should show enhance button again
    expect(screen.getByText('Enhance Prompt')).toBeInTheDocument();
    expect(screen.queryByText('Use This')).not.toBeInTheDocument();
  });

  it('shows error message when API call fails', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'cat' });
    });

    apiClient.enhancePrompt.mockRejectedValue(new Error('API Error'));

    render(<PromptEnhancer />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText(/API Error/i)).toBeInTheDocument();
      expect(screen.getByText('⚠')).toBeInTheDocument();
    });
  });

});
