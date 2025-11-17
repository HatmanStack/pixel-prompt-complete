/**
 * Integration Test: Generate Images Flow
 * Tests the complete user workflow from entering a prompt to viewing results
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import GenerationPanel from '../../components/generation/GenerationPanel';
import { AppProvider } from '../../context/AppContext';
import { ToastProvider } from '../../context/ToastContext';
import * as apiClient from '../../api/client';
import {
  mockGenerateResponse,
  mockJobStatusPending,
  mockJobStatusPartial,
  mockJobStatusCompleted
} from '../fixtures/apiResponses';

// Mock the API client
vi.mock('../../api/client');

describe('Generate Images Flow - Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('completes full generation flow: prompt → generate → poll → display results', async () => {
    const user = userEvent.setup();

    // Mock API responses
    apiClient.generateImages.mockResolvedValue(mockGenerateResponse);

    // Mock polling sequence: pending → partial → completed
    apiClient.getJobStatus
      .mockResolvedValueOnce(mockJobStatusPending)
      .mockResolvedValueOnce(mockJobStatusPartial)
      .mockResolvedValue(mockJobStatusCompleted);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    // Step 1: User enters prompt
    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'a beautiful sunset');

    expect(promptInput).toHaveValue('a beautiful sunset');

    // Step 2: User adjusts parameters
    const stepsSlider = screen.getByLabelText(/sampling steps/i);
    const guidanceSlider = screen.getByLabelText(/guidance scale/i);

    // For range inputs, use fireEvent to change the value
    fireEvent.change(stepsSlider, { target: { value: '30' } });

    // Step 3: User clicks generate button
    const generateButton = screen.getByRole('button', { name: /generate images/i });
    expect(generateButton).not.toBeDisabled();

    await user.click(generateButton);

    // Step 4: Verify API call made
    await waitFor(() => {
      expect(apiClient.generateImages).toHaveBeenCalledWith(
        'a beautiful sunset',
        expect.objectContaining({
          steps: 30
        })
      );
    });

    // Step 5: Verify loading state appears
    await waitFor(() => {
      expect(screen.getByText(/generating/i)).toBeInTheDocument();
    });

    // Step 6: Verify polling starts
    await waitFor(() => {
      expect(apiClient.getJobStatus).toHaveBeenCalledWith('test-job-123');
    }, { timeout: 3000 });

    // Step 7: Verify progress text updates
    await waitFor(() => {
      expect(screen.getByText(/Generating: 0 \/ 9 models complete/i)).toBeInTheDocument();
    });

    // Step 8: Verify partial results appear
    await waitFor(() => {
      expect(screen.getByText(/Generating: 3 \/ 9 models complete/i)).toBeInTheDocument();
    }, { timeout: 5000 });

    // Step 9: Verify completed images render
    await waitFor(() => {
      expect(screen.getByAltText(/Generated image from DALL-E 3/i)).toBeInTheDocument();
    }, { timeout: 5000 });

    // Step 10: Verify all images complete
    await waitFor(() => {
      expect(screen.getByText(/All images generated!/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    // Step 11: Verify all 9 images are displayed
    await waitFor(() => {
      const images = screen.getAllByRole('img');
      // Filter out any UI images, focus on generated images
      const generatedImages = images.filter(img =>
        img.alt && img.alt.includes('Generated image')
      );
      expect(generatedImages.length).toBe(9);
    });
  }, 15000); // 15 second timeout for full flow

  it('handles partial results with some model failures', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockResolvedValue(mockGenerateResponse);

    const partialWithErrors = {
      ...mockJobStatusCompleted,
      status: 'partial',
      completedModels: 7,
      results: [
        ...mockJobStatusCompleted.results.slice(0, 7),
        { model: 'Model 8', status: 'error', error: 'Generation failed' },
        { model: 'Model 9', status: 'error', error: 'API timeout' }
      ]
    };

    apiClient.getJobStatus.mockResolvedValue(partialWithErrors);

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

    // Wait for partial completion
    await waitFor(() => {
      expect(screen.getByText(/7 \/ 9 models complete/i)).toBeInTheDocument();
    }, { timeout: 5000 });

    // Verify error states are shown
    await waitFor(() => {
      expect(screen.getByText('Generation failed')).toBeInTheDocument();
    });
  }, 10000);

  it('allows user to generate multiple times sequentially', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockResolvedValue(mockGenerateResponse);
    apiClient.getJobStatus.mockResolvedValue(mockJobStatusCompleted);

    render(
      <ToastProvider>
        <AppProvider>
          <GenerationPanel />
        </AppProvider>
      </ToastProvider>
    );

    // First generation
    const promptInput = screen.getByLabelText(/image prompt/i);
    await user.type(promptInput, 'first prompt');

    const generateButton = screen.getByRole('button', { name: /generate images/i });
    await user.click(generateButton);

    await waitFor(() => {
      expect(apiClient.generateImages).toHaveBeenCalledWith(
        'first prompt',
        expect.any(Object)
      );
    });

    // Wait for completion
    await waitFor(() => {
      expect(screen.getByText(/All images generated!/i)).toBeInTheDocument();
    }, { timeout: 5000 });

    // Second generation
    await user.clear(promptInput);
    await user.type(promptInput, 'second prompt');
    await user.click(generateButton);

    await waitFor(() => {
      expect(apiClient.generateImages).toHaveBeenCalledWith(
        'second prompt',
        expect.any(Object)
      );
    });

    expect(apiClient.generateImages).toHaveBeenCalledTimes(2);
  }, 10000);

  it('shows waiting state for all models initially', async () => {
    const user = userEvent.setup();

    apiClient.generateImages.mockResolvedValue(mockGenerateResponse);
    apiClient.getJobStatus.mockResolvedValue(mockJobStatusPending);

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

    // Wait for generation to start
    await waitFor(() => {
      expect(apiClient.getJobStatus).toHaveBeenCalled();
    }, { timeout: 3000 });

    // Most models should show "Waiting..." or "Generating..."
    await waitFor(() => {
      const waitingTexts = screen.queryAllByText(/waiting|generating/i);
      expect(waitingTexts.length).toBeGreaterThan(5);
    });
  }, 8000);
});
