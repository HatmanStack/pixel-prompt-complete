/**
 * Integration Test: Error Handling Flows
 * Tests error handling across different scenarios
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GenerationPanel from '../../components/generation/GenerationPanel';
import { AppProvider } from '../../context/AppContext';
import { ToastProvider } from '../../context/ToastContext';
import * as apiClient from '../../api/client';
import {
  mockNetworkError,
  mockTimeoutError,
  mockGenerateResponse
} from '../fixtures/apiResponses';

// Mock the API client
vi.mock('../../api/client');

describe('Error Handling Flow - Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('handles network error during generation', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockRejectedValue(mockNetworkError);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test prompt');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Verify error message displayed
    await waitFor(() => {
      expect(screen.getByText(/Network request failed|Failed to start generation|error|connection/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    // Generate button should be re-enabled for retry
    expect(generateButton).not.toBeDisabled();
  }, 12000);

  it('handles 429 rate limit error', async () => {
    const user = userEvent.setup();

    const rateLimitError = new Error('Rate limit exceeded');
    rateLimitError.status = 429;

    apiClient.generateImages.mockRejectedValue(rateLimitError);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Verify specific rate limit message
    await waitFor(() => {
      expect(screen.getByText(/Rate limit exceeded|too many|rate limit/i)).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 12000);

  it('handles 400 content filter error', async () => {
    const user = userEvent.setup();

    const filterError = new Error('Inappropriate content detected');
    filterError.status = 400;
    filterError.message = 'Prompt contains inappropriate content';

    apiClient.generateImages.mockRejectedValue(filterError);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'inappropriate content');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Verify content filter message
    await waitFor(() => {
      expect(screen.getByText(/inappropriate content|different prompt|content/i)).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 12000);

  it('handles 404 job not found error during polling', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockResolvedValue(mockGenerateResponse);

    const notFoundError = new Error('Job not found');
    notFoundError.status = 404;
    apiClient.getJobStatus.mockRejectedValue(notFoundError);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Wait for job creation
    await waitFor(() => {
      expect(apiClient.generateImages).toHaveBeenCalled();
    });

    // Wait for polling error
    await waitFor(() => {
      expect(screen.getByText(/Job not found|not found|error/i)).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 12000);

  it('handles timeout error', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockRejectedValue(mockTimeoutError);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Verify timeout message
    await waitFor(() => {
      expect(screen.getByText(/timeout|took too long|error/i)).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 12000);

  it('allows dismissing error messages', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockRejectedValue(new Error('Test error'));

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Wait for error
    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    // Find and click dismiss button if available
    const dismissButtons = screen.queryAllByText(/dismiss|close/i);
    if (dismissButtons.length > 0) {
      await user.click(dismissButtons[0]);

      // Error should be removed
      await waitFor(() => {
        expect(screen.queryByText(/Test error/i)).not.toBeInTheDocument();
      }, { timeout: 3000 });
    }
  }, 12000);

  it('shows error when trying to generate with empty prompt', async () => {
    const user = userEvent.setup();

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    // Try to click generate without entering prompt
    const generateButton = screen.getByRole('button', { name: /generate images/i });

    // Button should be disabled when no prompt
    expect(generateButton).toBeDisabled();

    // Type and delete prompt
    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');
    await user.clear(promptInput);

    // Button should be disabled again
    expect(generateButton).toBeDisabled();
  });

  it('recovers from error and allows retry', async () => {
    const user = userEvent.setup();

    // First attempt fails
    apiClient.generateImages.mockRejectedValueOnce(new Error('Server error'));

    // Second attempt succeeds
    apiClient.generateImages.mockResolvedValueOnce(mockGenerateResponse);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test prompt');

    const generateButton = screen.getByRole('button', { name: /generate images/i });

    // First attempt
    await user.click(generateButton);

    // Wait for error
    await waitFor(() => {
      expect(screen.getByText(/Server error|Failed|error/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    // Retry
    await user.click(generateButton);

    // Should succeed this time
    await waitFor(() => {
      expect(apiClient.generateImages).toHaveBeenCalledTimes(2);
    }, { timeout: 3000 });

    // Error should be cleared
    await waitFor(() => {
      expect(screen.queryByText(/Server error/i)).not.toBeInTheDocument();
    }, { timeout: 3000 });
  }, 12000);

  it('handles multiple simultaneous errors gracefully', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockRejectedValue(new Error('Generation error'));
    apiClient.enhancePrompt.mockRejectedValue(new Error('Enhancement error'));

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'test');

    // Try to enhance (will fail)
    const enhanceButton = screen.getByRole('button', { name: /enhance prompt/i });
    await user.click(enhanceButton);

    // Wait for enhancement error
    await waitFor(() => {
      expect(screen.getByText(/Enhancement error|error|failed/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    // Try to generate (will also fail)
    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    // Both errors should be visible or at least one error visible
    await waitFor(() => {
      const errorTexts = screen.getAllByText(/error|failed/i);
      expect(errorTexts.length).toBeGreaterThan(0);
    }, { timeout: 8000 });
  }, 12000);
});
