/**
 * OutpaintControls Component
 * Outpainting preset buttons for each model column
 */

import { useState, type FC, type KeyboardEvent } from 'react';
import { outpaintImage } from '@/api/client';
import { useAppStore } from '@/stores/useAppStore';
import { useIteration } from '@/hooks/useIteration';
import type { ModelName, OutpaintPreset } from '@/types';

interface OutpaintControlsProps {
  model: ModelName;
}

const PRESETS: { value: OutpaintPreset; label: string }[] = [
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
  { value: '1:1', label: '1:1' },
  { value: '4:3', label: '4:3' },
  { value: 'expand_all', label: 'Expand' },
];

export const OutpaintControls: FC<OutpaintControlsProps> = ({ model }) => {
  const { currentSession } = useAppStore();
  const { isAtLimit, isEnabled } = useIteration(model);

  const [selectedPreset, setSelectedPreset] = useState<OutpaintPreset | null>(null);
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const column = currentSession?.models[model];
  const latestIteration = column?.iterations.slice(-1)[0];

  const handleOutpaint = async () => {
    if (!currentSession || !selectedPreset || !latestIteration || isAtLimit || !isEnabled) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await outpaintImage(
        currentSession.sessionId,
        model,
        latestIteration.index,
        selectedPreset,
        prompt,
      );
      setSelectedPreset(null);
      setPrompt('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to outpaint');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleOutpaint();
    } else if (e.key === 'Escape') {
      setSelectedPreset(null);
      setPrompt('');
    }
  };

  // Don't show if at limit, no iterations, or model not enabled
  if (isAtLimit || !latestIteration || !isEnabled) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2 p-2 bg-gray-50 dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
      <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">Expand image:</span>

      {/* Preset buttons */}
      <div className="flex flex-wrap gap-1">
        {PRESETS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setSelectedPreset(selectedPreset === value ? null : value)}
            className={`
              px-2 py-1 text-xs rounded
              transition-colors
              focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1
              ${
                selectedPreset === value
                  ? 'bg-accent text-white'
                  : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
              }
            `}
            aria-pressed={selectedPreset === value}
            aria-label={`Outpaint to ${label} aspect ratio`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Error message */}
      {error && (
        <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
          {error}
        </div>
      )}

      {/* Prompt input (shown when preset selected) */}
      {selectedPreset && (
        <div className="flex gap-2">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe expanded area..."
            className="
              flex-1 px-2 py-1 text-sm rounded border
              border-gray-300 dark:border-gray-600
              bg-white dark:bg-gray-800
              text-gray-900 dark:text-gray-100
              placeholder-gray-400 dark:placeholder-gray-500
              focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent
              disabled:opacity-50
            "
            onKeyDown={handleKeyDown}
            disabled={isSubmitting}
            aria-label="Enter description for expanded area"
          />
          <button
            onClick={handleOutpaint}
            disabled={isSubmitting}
            className="
              px-3 py-1 text-sm rounded
              bg-accent text-white
              hover:bg-accent/90
              focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
            "
          >
            {isSubmitting ? (
              <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              'Expand'
            )}
          </button>
        </div>
      )}
    </div>
  );
};

export default OutpaintControls;
