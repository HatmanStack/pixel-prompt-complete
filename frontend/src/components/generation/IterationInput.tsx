/**
 * IterationInput Component
 * Per-column text input for iteration prompts with warning display
 */

import { useState, type FC, type KeyboardEvent } from 'react';
import { useIteration } from '@/hooks/useIteration';
import type { ModelName } from '@/types';

interface IterationInputProps {
  model: ModelName;
}

export const IterationInput: FC<IterationInputProps> = ({ model }) => {
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { iterate, isAtLimit, showWarning, remainingIterations, isEnabled } =
    useIteration(model);

  const handleSubmit = async () => {
    if (!prompt.trim() || isAtLimit || isSubmitting || !isEnabled) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await iterate(prompt);
      setPrompt('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to iterate');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      setPrompt('');
    }
  };

  if (!isEnabled) {
    return (
      <div className="text-sm text-gray-400 text-center p-2">
        Model not enabled
      </div>
    );
  }

  if (isAtLimit) {
    return (
      <div className="text-sm text-gray-500 dark:text-gray-400 text-center p-2 bg-gray-100 dark:bg-gray-800 rounded">
        Maximum iterations reached (7)
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Warning message */}
      {showWarning && (
        <div className="text-sm text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 p-2 rounded border border-amber-200 dark:border-amber-800">
          {remainingIterations} iteration{remainingIterations !== 1 ? 's' : ''}{' '}
          remaining
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
          {error}
        </div>
      )}

      {/* Input and button */}
      <div className="flex gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Refine this image..."
          className="
            flex-1 px-3 py-2 rounded border
            border-gray-300 dark:border-gray-600
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent
            disabled:opacity-50 disabled:cursor-not-allowed
            text-sm
          "
          onKeyDown={handleKeyDown}
          disabled={isSubmitting}
          aria-label={`Enter iteration prompt for ${model}`}
        />
        <button
          onClick={handleSubmit}
          disabled={!prompt.trim() || isSubmitting}
          className="
            px-4 py-2 rounded
            bg-accent text-white
            hover:bg-accent/90
            focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors
            text-sm font-medium
          "
          aria-label="Submit iteration"
        >
          {isSubmitting ? (
            <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            'Go'
          )}
        </button>
      </div>
    </div>
  );
};

export default IterationInput;
