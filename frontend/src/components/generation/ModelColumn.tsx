/**
 * ModelColumn Component
 * Displays a single model's images vertically with all iterations
 */

import type { FC } from 'react';
import { IterationCard } from './IterationCard';
import { IterationInput } from './IterationInput';
import { OutpaintControls } from './OutpaintControls';
import type { ModelName, ModelColumn as ModelColumnType, Iteration } from '@/types';
import { MODEL_DISPLAY_NAMES } from '@/types';
import { useIteration } from '@/hooks/useIteration';

interface ModelColumnProps {
  model: ModelName;
  column: ModelColumnType;
  isSelected: boolean;
  onToggleSelect: () => void;
  onImageExpand?: (model: ModelName, iteration: Iteration) => void;
}

/**
 * Checkbox component
 */
const Checkbox: FC<{
  checked: boolean;
  onChange: () => void;
  'aria-label': string;
}> = ({ checked, onChange, 'aria-label': ariaLabel }) => (
  <label className="relative inline-flex items-center cursor-pointer">
    <input
      type="checkbox"
      checked={checked}
      onChange={onChange}
      className="sr-only peer"
      aria-label={ariaLabel}
    />
    <div
      className="
        w-5 h-5 rounded border-2
        peer-checked:bg-accent peer-checked:border-accent
        border-gray-300 dark:border-gray-600
        peer-focus:ring-2 peer-focus:ring-accent peer-focus:ring-offset-2
        transition-colors
        flex items-center justify-center
      "
    >
      {checked && (
        <svg
          className="w-3 h-3 text-white"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M5 13l4 4L19 7"
          />
        </svg>
      )}
    </div>
  </label>
);

/**
 * Disabled model state
 */
const DisabledState: FC<{ model: ModelName }> = ({ model }) => (
  <div className="flex-1 flex flex-col items-center justify-center p-4 bg-gray-100 dark:bg-gray-800 rounded-lg">
    <svg
      className="w-8 h-8 text-gray-400 mb-2"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
      />
    </svg>
    <p className="text-sm text-gray-500 dark:text-gray-400 text-center">
      {MODEL_DISPLAY_NAMES[model]} is not enabled
    </p>
  </div>
);

export const ModelColumn: FC<ModelColumnProps> = ({
  model,
  column,
  isSelected,
  onToggleSelect,
  onImageExpand,
}) => {
  const { isAtLimit } = useIteration(model);

  if (!column.enabled) {
    return (
      <div className="flex flex-col gap-4 min-w-[250px] max-w-[300px] flex-shrink-0">
        {/* Header */}
        <div className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            {MODEL_DISPLAY_NAMES[model]}
          </h3>
        </div>

        <DisabledState model={model} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 min-w-[250px] max-w-[300px] flex-shrink-0">
      {/* Header with model name and checkbox */}
      <div className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900 rounded-lg sticky top-0 z-20">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">
          {MODEL_DISPLAY_NAMES[model]}
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {column.iterations.length}/7
          </span>
          <Checkbox
            checked={isSelected}
            onChange={onToggleSelect}
            aria-label={`Select ${MODEL_DISPLAY_NAMES[model]} for batch editing`}
          />
        </div>
      </div>

      {/* Iterations list */}
      <div
        className="flex flex-col gap-2 overflow-y-auto max-h-[60vh] pr-1 scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600"
        role="list"
        aria-label={`${MODEL_DISPLAY_NAMES[model]} iterations`}
      >
        {column.iterations.length === 0 ? (
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center p-4 bg-gray-100 dark:bg-gray-800 rounded-lg">
            No images yet
          </div>
        ) : (
          column.iterations.map((iteration) => (
            <div key={iteration.index} role="listitem">
              <IterationCard
                model={model}
                iteration={iteration}
                onExpand={() => onImageExpand?.(model, iteration)}
              />
            </div>
          ))
        )}
      </div>

      {/* Per-column input */}
      {!isAtLimit && column.enabled && <IterationInput model={model} />}

      {/* Outpaint controls */}
      <OutpaintControls model={model} />
    </div>
  );
};

export default ModelColumn;
