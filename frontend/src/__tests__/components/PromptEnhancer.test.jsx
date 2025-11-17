/**
 * Tests for PromptEnhancer Component
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PromptEnhancer from '../../components/generation/PromptEnhancer';
import * as apiClient from '../../api/client';

// Mock the API client
vi.mock('../../api/client');

describe('PromptEnhancer', () => {
  const mockOnUsePrompt = vi.fn();

  beforeEach(() => {
    mockOnUsePrompt.mockClear();
    vi.clearAllMocks();
  });

  it('renders enhance button with icon', () => {
    render(<PromptEnhancer currentPrompt="test" onUsePrompt={mockOnUsePrompt} />);
    expect(screen.getByText('Enhance Prompt')).toBeInTheDocument();
    expect(screen.getByText('✨')).toBeInTheDocument();
  });

  it('button is disabled when no prompt is entered', () => {
    render(<PromptEnhancer currentPrompt="" onUsePrompt={mockOnUsePrompt} />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).toBeDisabled();
  });

  it('button is disabled when prompt is only whitespace', () => {
    render(<PromptEnhancer currentPrompt="   " onUsePrompt={mockOnUsePrompt} />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).toBeDisabled();
  });

  it('button is enabled when valid prompt is entered', () => {
    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).not.toBeDisabled();
  });

  it('button is disabled when disabled prop is true', () => {
    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} disabled={true} />);
    const button = screen.getByRole('button', { name: /Enhance Prompt/i });
    expect(button).toBeDisabled();
  });

  it('shows loading state when enhancing', async () => {
    const user = userEvent.setup();

    // Mock API call that takes time
    apiClient.enhancePrompt.mockImplementation(() => new Promise(() => {}));

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(screen.getByText('Enhancing...')).toBeInTheDocument();
  });

  it('calls API and shows enhanced result on success', async () => {
    const user = userEvent.setup();
    const mockResponse = {
      short_prompt: 'Enhanced short version',
      long_prompt: 'Enhanced long version with more details'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

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
    const mockResponse = {
      short_prompt: 'Short version',
      long_prompt: 'Long version'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Short')).toBeInTheDocument();
      expect(screen.getByText('Long')).toBeInTheDocument();
    });
  });

  it('toggles between short and long enhanced prompts', async () => {
    const user = userEvent.setup();
    const mockResponse = {
      short_prompt: 'Short version',
      long_prompt: 'Long version with details'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

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
    const mockResponse = {
      short_prompt: 'Short',
      long_prompt: 'Long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Use This')).toBeInTheDocument();
      expect(screen.getByText('Discard')).toBeInTheDocument();
    });
  });

  it('calls onUsePrompt with short version when "Use This" is clicked', async () => {
    const user = userEvent.setup();
    const mockResponse = {
      short_prompt: 'Enhanced short',
      long_prompt: 'Enhanced long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Use This')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Use This'));

    expect(mockOnUsePrompt).toHaveBeenCalledWith('Enhanced short');
  });

  it('calls onUsePrompt with long version when long is selected', async () => {
    const user = userEvent.setup();
    const mockResponse = {
      short_prompt: 'Enhanced short',
      long_prompt: 'Enhanced long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText('Long')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Long' }));
    await user.click(screen.getByText('Use This'));

    expect(mockOnUsePrompt).toHaveBeenCalledWith('Enhanced long');
  });

  it('clears enhanced result when "Discard" is clicked', async () => {
    const user = userEvent.setup();
    const mockResponse = {
      short_prompt: 'Enhanced short',
      long_prompt: 'Enhanced long'
    };

    apiClient.enhancePrompt.mockResolvedValue(mockResponse);

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

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

    apiClient.enhancePrompt.mockRejectedValue(new Error('API Error'));

    render(<PromptEnhancer currentPrompt="cat" onUsePrompt={mockOnUsePrompt} />);

    await user.click(screen.getByRole('button', { name: /Enhance Prompt/i }));

    await waitFor(() => {
      expect(screen.getByText(/API Error/i)).toBeInTheDocument();
      expect(screen.getByText('⚠')).toBeInTheDocument();
    });
  });

});
