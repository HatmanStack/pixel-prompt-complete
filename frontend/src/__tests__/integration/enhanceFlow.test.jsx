/**
 * Integration Test: Prompt Enhancement Flow
 * Tests the complete prompt enhancement workflow
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GenerationPanel from '../../components/generation/GenerationPanel';
import { AppProvider } from '../../context/AppContext';
import { ToastProvider } from '../../context/ToastContext';
import * as apiClient from '../../api/client';
import { mockEnhanceResponse, mockGenerateResponse, mockJobStatusCompleted } from '../fixtures/apiResponses';

// Mock the API client
vi.mock('../../api/client');

describe('Enhance Prompt Flow - Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('completes full enhance flow: enter prompt → enhance → use enhanced → generate', async () => {
    const user = userEvent.setup();

    // Mock API responses
    apiClient.enhancePrompt.mockResolvedValue(mockEnhanceResponse);
    apiClient.generateImages.mockResolvedValue(mockGenerateResponse);
    apiClient.getJobStatus.mockResolvedValue(mockJobStatusCompleted);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    // Step 1: User enters short prompt
    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'cat');

    expect(promptInput).toHaveValue('cat');

    // Step 2: User clicks enhance button
    const enhanceButton = screen.getByRole('button', { name: /enhance prompt/i });
    expect(enhanceButton).not.toBeDisabled();

    await user.click(enhanceButton);

    // Step 3: Verify enhance API called
    await waitFor(() => {
      expect(apiClient.enhancePrompt).toHaveBeenCalledWith('cat');
    });

    // Step 4: Verify enhanced result displayed
    await waitFor(() => {
      expect(screen.getByText('Enhanced Prompt')).toBeInTheDocument();
    });

    // Verify original and enhanced shown
    expect(screen.getByText('cat')).toBeInTheDocument();
    expect(screen.getByText(/orange tabby cat on a velvet cushion/i)).toBeInTheDocument();

    // Step 5: User toggles to long version
    const longButton = screen.getByRole('button', { name: 'Long' });
    await user.click(longButton);

    // Verify long version shown
    expect(screen.getByText(/majestic orange tabby cat sitting regally/i)).toBeInTheDocument();

    // Step 6: User clicks "Use This" to apply enhanced prompt
    const useButton = screen.getByText('Use This');
    await user.click(useButton);

    // Step 7: Verify prompt input updated with enhanced text
    await waitFor(() => {
      expect(promptInput.value).toContain('majestic orange tabby cat');
    });

    // Step 8: User generates with enhanced prompt
    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Step 9: Verify generate called with enhanced prompt
    await waitFor(() => {
      expect(apiClient.generateImages).toHaveBeenCalledWith(
        expect.stringContaining('majestic orange tabby cat'),
        expect.any(Object)
      );
    });
  }, 15000);

  it('allows discarding enhanced prompt and starting over', async () => {
    const user = userEvent.setup();

    apiClient.enhancePrompt.mockResolvedValue(mockEnhanceResponse);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    // Enhance a prompt
    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'cat');

    const enhanceButton = screen.getByRole('button', { name: /enhance prompt/i });
    await user.click(enhanceButton);

    // Wait for enhanced result
    await waitFor(() => {
      expect(screen.getByText('Enhanced Prompt')).toBeInTheDocument();
    });

    // Discard enhanced prompt
    const discardButton = screen.getByText('Discard');
    await user.click(discardButton);

    // Verify back to enhance button
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /enhance prompt/i })).toBeInTheDocument();
    });

    // Original prompt should still be in input
    expect(promptInput).toHaveValue('cat');
  }, 10000);

  it('handles enhancement error gracefully', async () => {
    const user = userEvent.setup();

    apiClient.enhancePrompt.mockRejectedValue(new Error('Enhancement service unavailable'));

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');

    const enhanceButton = screen.getByRole('button', { name: /enhance prompt/i });
    await user.click(enhanceButton);

    // Verify error message shown
    await waitFor(() => {
      expect(screen.getByText(/Enhancement service unavailable/i)).toBeInTheDocument();
    });

    // Enhance button should still be available for retry
    expect(screen.getByRole('button', { name: /enhance prompt/i })).toBeInTheDocument();
  }, 10000);

  it('shows loading state during enhancement', async () => {
    const user = userEvent.setup();

    // Delay the response to see loading state
    apiClient.enhancePrompt.mockImplementation(() =>
      new Promise(resolve => setTimeout(() => resolve(mockEnhanceResponse), 1000))
    );

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'cat');

    const enhanceButton = screen.getByRole('button', { name: /enhance prompt/i });
    await user.click(enhanceButton);

    // Verify loading state
    expect(screen.getByText('Enhancing...')).toBeInTheDocument();

    // Wait for completion
    await waitFor(() => {
      expect(screen.getByText('Enhanced Prompt')).toBeInTheDocument();
    }, { timeout: 2000 });
  }, 5000);

  it('allows switching between short and long versions before using', async () => {
    const user = userEvent.setup();

    apiClient.enhancePrompt.mockResolvedValue(mockEnhanceResponse);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'cat');

    const enhanceButton = screen.getByRole('button', { name: /enhance prompt/i });
    await user.click(enhanceButton);

    await waitFor(() => {
      expect(screen.getByText('Enhanced Prompt')).toBeInTheDocument();
    });

    // Toggle between short and long multiple times
    const shortButton = screen.getByRole('button', { name: 'Short' });
    const longButton = screen.getByRole('button', { name: 'Long' });

    // Should start with short selected
    expect(screen.getByText(/orange tabby cat on a velvet cushion/i)).toBeInTheDocument();

    // Switch to long
    await user.click(longButton);
    expect(screen.getByText(/majestic orange tabby cat sitting regally/i)).toBeInTheDocument();

    // Switch back to short
    await user.click(shortButton);
    expect(screen.getByText(/orange tabby cat on a velvet cushion/i)).toBeInTheDocument();
    expect(screen.queryByText(/majestic orange tabby cat sitting regally/i)).not.toBeInTheDocument();

    // Use short version
    const useButton = screen.getByText('Use This');
    await user.click(useButton);

    // Verify short version applied
    await waitFor(() => {
      expect(promptInput.value).toContain('orange tabby cat on a velvet cushion');
    });
  }, 10000);
});
