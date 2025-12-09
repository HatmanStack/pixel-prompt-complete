/**
 * MultiIterateInput Component
 * Shared input for batch iteration when multiple models are selected
 */

import { useState, type FC, type KeyboardEvent } from 'react';
import { useMultiIterate } from '@/hooks/useIteration';

interface MultiIterateInputProps {
  selectedCount: number;
}

export const MultiIterateInput: FC<MultiIterateInputProps> = ({
  selectedCount,
}) => {
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { iterateSelected, canIterate } = useMultiIterate();

  const handleSubmit = async () => {
    if (!prompt.trim() || isSubmitting || !canIterate) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await iterateSelected(prompt);
      setPrompt('');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to iterate on selected models'
      );
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

  return (
    <div className="flex flex-col gap-2 p-3 bg-accent/10 dark:bg-accent/5 rounded-lg border border-accent/20">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Edit {selectedCount} image{selectedCount > 1 ? 's' : ''}:
        </span>
      </div>

      {/* Error message */}
      {error && (
        <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Apply to all selected..."
          className="
            flex-1 px-3 py-2 rounded border
            border-gray-300 dark:border-gray-600
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent
            disabled:opacity-50 disabled:cursor-not-allowed
          "
          onKeyDown={handleKeyDown}
          disabled={isSubmitting}
          aria-label="Enter prompt to apply to all selected models"
        />

        <button
          onClick={handleSubmit}
          disabled={!prompt.trim() || isSubmitting || !canIterate}
          className="
            px-4 py-2 rounded
            bg-accent text-white
            hover:bg-accent/90
            focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors
            font-medium
          "
        >
          {isSubmitting ? (
            <span className="inline-flex items-center gap-2">
              <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Applying...
            </span>
          ) : (
            'Apply'
          )}
        </button>
      </div>
    </div>
  );
};

export default MultiIterateInput;
