/**
 * GenerationPanel Component
 * Main panel with 4-column layout for session-based image generation
 */

import { useEffect, useState, type FC } from 'react';
import { useAppStore } from '@/stores/useAppStore';
import { useSessionPolling } from '@/hooks/useSessionPolling';
import { generateSession } from '@/api/client';
import { useToast } from '@/stores/useToastStore';
import { useSound } from '@/hooks/useSound';
import PromptInput from './PromptInput';
import RandomPromptButton from '@/components/features/generation/RandomPromptButton';
import PromptEnhancer from './PromptEnhancer';
import GenerateButton from './GenerateButton';
import { ModelColumn } from './ModelColumn';
import { MultiIterateInput } from './MultiIterateInput';
import GalleryBrowser from '@/components/gallery/GalleryBrowser';
import { ErrorBoundary } from '@/components/features/errors/ErrorBoundary';
import { ImageModal } from '@/components/features/generation/ImageModal';
import type {
  ModelName,
  ModelColumn as ModelColumnType,
  Iteration,
} from '@/types';
import { MODELS } from '@/types';

interface ApiError extends Error {
  status?: number;
}

/**
 * Create an empty model column for display when no session exists
 */
function createEmptyColumn(model: ModelName): ModelColumnType {
  return {
    name: model,
    enabled: true,
    status: 'pending',
    iterations: [],
  };
}

/**
 * Progress bar component
 */
const ProgressBar: FC<{ session: ReturnType<typeof useAppStore.getState>['currentSession'] }> = ({
  session,
}) => {
  if (!session) return null;

  // Count completed iterations across all models
  let completed = 0;
  let total = 0;

  for (const model of MODELS) {
    const column = session.models[model];
    if (column && column.enabled) {
      total += column.iterations.length;
      completed += column.iterations.filter((i) => i.status === 'completed').length;
    }
  }

  const percent = total > 0 ? (completed / total) * 100 : 0;
  const text =
    session.status === 'pending'
      ? 'Starting...'
      : session.status === 'in_progress'
        ? `Generating: ${completed} / ${total} complete`
        : session.status === 'completed'
          ? 'All images generated!'
          : session.status === 'partial'
            ? 'Generation completed with some errors'
            : 'Generation failed';

  return (
    <div
      className="flex flex-col gap-2"
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Generation progress"
    >
      <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-accent to-accent/70 rounded-full transition-all duration-200"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p
        className="text-sm text-gray-600 dark:text-gray-400 text-center m-0"
        aria-live="polite"
      >
        {text}
      </p>
    </div>
  );
};

/**
 * Error banner component
 */
const ErrorBanner: FC<{ error: string; onDismiss: () => void }> = ({
  error,
  onDismiss,
}) => (
  <div
    className="
      flex items-center gap-4 p-4
      bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-md
      text-red-700 dark:text-red-300 text-sm
      animate-in slide-in-from-top-2 duration-200
    "
    role="alert"
  >
    <span className="text-xl">⚠</span>
    <span>{error}</span>
    <button
      className="
        ml-auto w-6 h-6
        flex items-center justify-center
        bg-transparent border-none
        text-red-600 dark:text-red-400 text-lg cursor-pointer
        transition-transform duration-150
        hover:scale-125
      "
      onClick={onDismiss}
      aria-label="Dismiss error"
    >
      ✕
    </button>
  </div>
);

export const GenerationPanel: FC = () => {
  const {
    prompt,
    currentSession,
    setCurrentSession,
    isGenerating,
    setIsGenerating,
    resetSession,
    selectedModels,
    toggleModelSelection,
  } = useAppStore();

  const { error: showError } = useToast();
  const { playSound } = useSound();

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [expandedImage, setExpandedImage] = useState<{
    model: ModelName;
    iteration: Iteration;
  } | null>(null);

  // Poll session status when we have a session ID
  const { error: pollingError } = useSessionPolling(
    currentSession?.sessionId ?? null,
    { enabled: isGenerating }
  );

  // Handle polling errors
  useEffect(() => {
    if (pollingError) {
      setIsGenerating(false);
      setErrorMessage(pollingError);
    }
  }, [pollingError, setIsGenerating]);

  // Play sound on completion
  useEffect(() => {
    if (
      currentSession &&
      !isGenerating &&
      ['completed', 'partial'].includes(currentSession.status)
    ) {
      playSound('swoosh');
    }
  }, [currentSession, isGenerating, playSound]);

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setErrorMessage('Please enter a prompt');
      return;
    }

    try {
      // Reset previous generation
      resetSession();
      setErrorMessage(null);
      setIsGenerating(true);
      playSound('click');

      // Call API to start generation
      const response = await generateSession(prompt);

      if (response.sessionId) {
        // Initialize session structure for polling
        const initialSession = {
          sessionId: response.sessionId,
          status: 'pending' as const,
          prompt,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          models: MODELS.reduce(
            (acc, model) => {
              acc[model] = createEmptyColumn(model);
              return acc;
            },
            {} as Record<ModelName, ModelColumnType>
          ),
        };
        setCurrentSession(initialSession);
      } else {
        throw new Error('No session ID received');
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
        const msg =
          'Prompt contains inappropriate content. Please try a different prompt.';
        setErrorMessage(msg);
        showError(msg);
      } else {
        const msg =
          error.message || 'Failed to start generation. Please try again.';
        setErrorMessage(msg);
        showError(msg);
      }
    }
  };

  // Handle image expansion
  const handleImageExpand = (model: ModelName, iteration: Iteration) => {
    if (iteration.status === 'completed' && iteration.imageUrl) {
      setExpandedImage({ model, iteration });
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
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

      // Escape to close modal
      if (e.key === 'Escape' && expandedImage) {
        setExpandedImage(null);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt, isGenerating, expandedImage]);

  // Legacy gallery handler - for backwards compatibility
  const handleGallerySelect = (
    gallery: { id: string; images: { model: string; url?: string }[] } | null
  ) => {
    // Legacy handler - can be extended to load sessions in future
    console.log('Gallery selected:', gallery?.id);
  };

  return (
    <article
      className="w-full flex flex-col gap-8 md:gap-6"
      aria-label="Image Generation"
    >
      {/* Input Section */}
      <section
        className="flex flex-col gap-6 md:gap-4"
        aria-labelledby="prompt-section-heading"
      >
        <h2 id="prompt-section-heading" className="sr-only">
          Create Your Image
        </h2>
        <PromptInput disabled={isGenerating} />

        <div className="flex gap-4 flex-col md:flex-row">
          <div className="flex-1">
            <RandomPromptButton disabled={isGenerating} />
          </div>
          <div className="flex-1">
            <PromptEnhancer disabled={isGenerating} />
          </div>
        </div>

        <div className="flex gap-4 items-start">
          <GenerateButton
            onClick={handleGenerate}
            isGenerating={isGenerating}
            disabled={!prompt.trim() || isGenerating}
          />

          {/* Multi-select input */}
          {selectedModels.size > 0 && (
            <div className="flex-1">
              <MultiIterateInput selectedCount={selectedModels.size} />
            </div>
          )}
        </div>

        {/* Error Message */}
        {errorMessage && (
          <ErrorBanner
            error={errorMessage}
            onDismiss={() => setErrorMessage(null)}
          />
        )}

        {/* Progress */}
        {isGenerating && <ProgressBar session={currentSession} />}
      </section>

      {/* 4-Column Layout */}
      <section
        className="flex gap-4 overflow-x-auto pb-4 snap-x snap-mandatory md:snap-none"
        aria-labelledby="models-section-heading"
      >
        <h2 id="models-section-heading" className="sr-only">
          Model Columns
        </h2>
        {MODELS.map((model) => {
          const column = currentSession?.models[model] ?? createEmptyColumn(model);
          return (
            <div key={model} className="snap-center">
              <ErrorBoundary componentName={`ModelColumn-${model}`}>
                <ModelColumn
                  model={model}
                  column={column}
                  isSelected={selectedModels.has(model)}
                  onToggleSelect={() => toggleModelSelection(model)}
                  onImageExpand={handleImageExpand}
                />
              </ErrorBoundary>
            </div>
          );
        })}
      </section>

      {/* Gallery Section */}
      <section aria-labelledby="gallery-section-heading">
        <h2 id="gallery-section-heading" className="sr-only">
          Previous Generations
        </h2>
        <ErrorBoundary componentName="GalleryBrowser">
          <GalleryBrowser onGallerySelect={handleGallerySelect} />
        </ErrorBoundary>
      </section>

      {/* Image Modal */}
      {expandedImage && (
        <ImageModal
          isOpen={!!expandedImage}
          onClose={() => setExpandedImage(null)}
          imageUrl={expandedImage.iteration.imageUrl || ''}
          model={expandedImage.model}
          iteration={expandedImage.iteration}
        />
      )}
    </article>
  );
};

export default GenerationPanel;
