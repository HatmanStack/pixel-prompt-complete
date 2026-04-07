/**
 * ModelColumn Component
 * Displays a single model's images vertically with all iterations
 */

import { memo, type FC, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { IterationCard } from './IterationCard';
import { IterationInput } from './IterationInput';
import { OutpaintControls } from './OutpaintControls';
import type { ModelName, ModelColumn as ModelColumnType, Iteration } from '@/types';
import { MODEL_DISPLAY_NAMES } from '@/types';
import { useIteration } from '@/hooks/useIteration';
import { MAX_ITERATIONS } from '@/config/constants';

interface ModelColumnProps {
  model: ModelName;
  column: ModelColumnType;
  isSelected: boolean;
  onToggleSelect: () => void;
  onImageExpand?: (model: ModelName, iteration: Iteration) => void;
  isFocused?: boolean;
  isCompressed?: boolean;
  onFocusToggle?: () => void;
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
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
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

export const ModelColumn: FC<ModelColumnProps> = memo(
  ({
    model,
    column,
    isSelected,
    onToggleSelect,
    onImageExpand,
    isFocused = false,
    isCompressed = false,
    onFocusToggle,
  }) => {
    const { isAtLimit } = useIteration(model);

    // When no focus is active, use the default min-w/max-w. When focus is active
    // the parent wrapper sets widths, so we let the column fill its container.
    const sizeClass =
      isFocused || isCompressed ? 'w-full' : 'min-w-[250px] max-w-[300px] flex-shrink-0';

    if (!column.enabled) {
      return (
        <div className={`flex flex-col gap-4 ${sizeClass}`}>
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

    const handleHeaderKeyDown = (e: ReactKeyboardEvent) => {
      if ((e.key === 'Enter' || e.key === ' ') && onFocusToggle) {
        e.preventDefault();
        onFocusToggle();
      }
    };

    return (
      <div className={`flex flex-col gap-4 transition-all duration-300 ease-in-out ${sizeClass}`}>
        {/* Header with model name and checkbox */}
        <div
          className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900 rounded-lg sticky top-0 z-20 cursor-pointer"
          onClick={onFocusToggle}
          onKeyDown={handleHeaderKeyDown}
          role="button"
          tabIndex={0}
          aria-expanded={isFocused}
          aria-label={`${isFocused ? 'Collapse' : 'Expand'} ${MODEL_DISPLAY_NAMES[model]} column`}
        >
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
            {MODEL_DISPLAY_NAMES[model]}
          </h3>
          {!isCompressed && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {column.iterations.length}/{MAX_ITERATIONS}
              </span>
              <Checkbox
                checked={isSelected}
                onChange={onToggleSelect}
                aria-label={`Select ${MODEL_DISPLAY_NAMES[model]} for batch editing`}
              />
            </div>
          )}
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
          ) : isCompressed ? (
            // Compressed: show only the latest iteration as a thumbnail
            (() => {
              const latest = column.iterations[column.iterations.length - 1];
              return (
                <div role="listitem">
                  <IterationCard
                    model={model}
                    iteration={latest}
                    onExpand={() => onImageExpand?.(model, latest)}
                  />
                </div>
              );
            })()
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

        {/* Per-column input (kept visible when compressed) */}
        {!isAtLimit && column.enabled && <IterationInput model={model} />}

        {/* Outpaint controls (hidden when compressed) */}
        {!isCompressed && <OutpaintControls model={model} />}
      </div>
    );
  },
);

export default ModelColumn;
