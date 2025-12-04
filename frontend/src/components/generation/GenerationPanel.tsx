/**
 * GenerationPanel Component
 * Main panel that integrates all generation components
 */

import { useEffect, useState, type FC } from 'react';
import { useAppStore } from '@/stores/useAppStore';
import useJobPolling from '@/hooks/useJobPolling';
import useImageLoader from '@/hooks/useImageLoader';
import { generateImages } from '@/api/client';
import { useToast } from '@/context/ToastContext';
import { useSound } from '@/hooks/useSound';
import PromptInput from './PromptInput';
import RandomPromptButton from '@/components/features/generation/RandomPromptButton';
import PromptEnhancer from './PromptEnhancer';
import GenerateButton from './GenerateButton';
import ImageGrid from './ImageGrid';
import GalleryBrowser from '@/components/gallery/GalleryBrowser';
import type { Job, ImageResult } from '@/types';

interface GalleryImage {
  model: string;
  url?: string;
  blobUrl?: string;
  timestamp?: string;
}

interface SelectedGalleryData {
  id: string;
  images: GalleryImage[];
  total: number;
}

interface GeneratedImage {
  model: string;
  status: 'pending' | 'loading' | 'completed' | 'error' | 'success';
  imageUrl?: string;
  image: string | null;
  error: string | null;
  completedAt?: string;
}

interface ApiError extends Error {
  status?: number;
}

export const GenerationPanel: FC = () => {
  const {
    prompt,
    currentJob,
    setCurrentJob,
    generatedImages,
    setGeneratedImages,
    isGenerating,
    setIsGenerating,
    resetGeneration,
  } = useAppStore();

  const { error: showError } = useToast();
  const { playSound } = useSound();

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [modelNames, setModelNames] = useState<string[]>([]);

  // Poll job status when we have a job ID
  const { jobStatus, error: pollingError } = useJobPolling(currentJob?.jobId, 2000);

  // Load images from S3
  const { images: loadedImages } = useImageLoader(jobStatus);

  // Update generated images when job status changes
  useEffect(() => {
    if (jobStatus) {
      setCurrentJob(jobStatus as Job);

      // Extract model names
      if (jobStatus.results) {
        const names = jobStatus.results.map((r) => r.model || 'Unknown');
        setModelNames(names);
      }

      // Update image states based on results and loaded images
      if (jobStatus.results) {
        const updatedImages = jobStatus.results.map((result, index) => ({
          model: result.model,
          status: result.status,
          imageUrl: result.url,
          image: loadedImages[index],
          error: result.error || null,
        })) as unknown as (ImageResult | null)[];

        setGeneratedImages(updatedImages);
      }

      // Check if job is complete
      if (
        jobStatus.status === 'completed' ||
        // @ts-expect-error - 'partial' may be returned by API
        jobStatus.status === 'partial'
      ) {
        setIsGenerating(false);
        playSound('swoosh');
      } else if (jobStatus.status === 'failed') {
        setIsGenerating(false);
        setErrorMessage('Generation failed. Please try again.');
      }
    }
  }, [jobStatus, loadedImages, setCurrentJob, setGeneratedImages, setIsGenerating, playSound]);

  // Handle polling errors
  useEffect(() => {
    if (pollingError) {
      setIsGenerating(false);
      setErrorMessage(pollingError);
    }
  }, [pollingError, setIsGenerating]);

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setErrorMessage('Please enter a prompt');
      return;
    }

    try {
      // Reset previous generation
      resetGeneration();
      setErrorMessage(null);
      setIsGenerating(true);
      playSound('click');

      // Call API to start generation
      const response = await generateImages(prompt);

      if (response.jobId) {
        setCurrentJob({
          jobId: response.jobId,
          status: 'in_progress',
        } as Job);
      } else {
        throw new Error('No job ID received');
      }
    } catch (err) {
      console.error('Generation error:', err);
      setIsGenerating(false);

      const error = err as ApiError;

      // Handle specific error codes
      if (error.status === 429) {
        const msg = 'Rate limit exceeded. Please try again later.';
        setErrorMessage(msg);
        showError(msg);
      } else if (error.status === 400 && error.message?.includes('filter')) {
        const msg = 'Prompt contains inappropriate content. Please try a different prompt.';
        setErrorMessage(msg);
        showError(msg);
      } else {
        const msg = error.message || 'Failed to start generation. Please try again.';
        setErrorMessage(msg);
        showError(msg);
      }
    }
  };

  // Listen for keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in inputs
      const activeTag = (document.activeElement as HTMLElement)?.tagName;
      const isTyping = ['INPUT', 'TEXTAREA'].includes(activeTag);

      // Ctrl+Enter to generate
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !isTyping) {
        if (!isGenerating && prompt.trim()) {
          handleGenerate();
        }
      }

      // Ctrl+R for random prompt
      if ((e.ctrlKey || e.metaKey) && e.key === 'r' && !isTyping) {
        e.preventDefault();
        if (!isGenerating) {
          const event = new CustomEvent('random-prompt-trigger');
          document.dispatchEvent(event);
        }
      }

      // Ctrl+E for enhance prompt
      if ((e.ctrlKey || e.metaKey) && e.key === 'e' && !isTyping) {
        e.preventDefault();
        if (!isGenerating && prompt.trim()) {
          const event = new CustomEvent('enhance-prompt-trigger');
          document.dispatchEvent(event);
        }
      }

      // Ctrl+Shift+D for download all images
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D' && !isTyping) {
        e.preventDefault();
        const event = new CustomEvent('download-all-trigger');
        document.dispatchEvent(event);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt, isGenerating]);

  const getProgressText = (): string => {
    if (!jobStatus || !jobStatus.results) return '';

    const completed = jobStatus.results.filter((r) => r.status === 'success').length;
    const total = jobStatus.results.length;

    if (completed === total) {
      return 'All images generated!';
    }

    return `Generating: ${completed} / ${total} models complete`;
  };

  // Handle gallery selection
  const handleGallerySelect = (gallery: SelectedGalleryData | null) => {
    if (!gallery) {
      return;
    }

    // Convert gallery images to generatedImages format
    const galleryImages: GeneratedImage[] = gallery.images.map((img, index) => ({
      model: img.model || `Model ${index + 1}`,
      status: 'completed' as const,
      imageUrl: img.url,
      image: img.blobUrl || img.url || null,
      error: null,
      completedAt: img.timestamp,
    }));

    setGeneratedImages(galleryImages as unknown as (ImageResult | null)[]);
    setModelNames(galleryImages.map((img) => img.model));
  };

  const progressPercent = jobStatus?.results
    ? (jobStatus.results.filter((r) => r.status === 'success').length / jobStatus.results.length) *
      100
    : 0;

  return (
    <div className="w-full flex flex-col gap-8 md:gap-6">
      {/* Input Section */}
      <div className="flex flex-col gap-6 md:gap-4">
        <PromptInput disabled={isGenerating} />

        <div className="flex gap-4 flex-col md:flex-row">
          <div className="flex-1">
            <RandomPromptButton disabled={isGenerating} />
          </div>
          <div className="flex-1">
            <PromptEnhancer disabled={isGenerating} />
          </div>
        </div>

        <GenerateButton
          onClick={handleGenerate}
          isGenerating={isGenerating}
          disabled={!prompt.trim() || isGenerating}
        />

        {/* Error Message */}
        {errorMessage && (
          <div
            className="
              flex items-center gap-4 p-4
              bg-error/10 border border-error rounded-md
              text-error text-sm
              animate-in slide-in-from-top-2 duration-200
            "
            role="alert"
          >
            <span className="text-xl">⚠</span>
            <span>{errorMessage}</span>
            <button
              className="
                ml-auto w-6 h-6
                flex items-center justify-center
                bg-transparent border-none
                text-error text-lg cursor-pointer
                transition-transform duration-150
                hover:scale-125
              "
              onClick={() => setErrorMessage(null)}
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}

        {/* Progress */}
        {isGenerating && (
          <div className="flex flex-col gap-2" aria-live="polite">
            <div className="w-full h-2 bg-secondary rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-accent to-accent-muted rounded-full transition-all duration-200"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <p className="text-sm text-text-secondary text-center m-0">{getProgressText()}</p>
          </div>
        )}
      </div>

      {/* Gallery Section */}
      <div>
        <GalleryBrowser onGallerySelect={handleGallerySelect} />
      </div>

      {/* Results Section */}
      <div className="w-full">
        <ImageGrid images={generatedImages} modelNames={modelNames} />
      </div>
    </div>
  );
};

export default GenerationPanel;
