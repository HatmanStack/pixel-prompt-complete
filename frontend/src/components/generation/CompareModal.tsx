/**
 * CompareModal Component
 * Full-screen comparison of 2-4 model images with iteration picker
 */

import { useState, useEffect, useRef, useCallback, type FC } from 'react';
import type { ModelName, Session } from '@/types';
import { MODEL_DISPLAY_NAMES } from '@/types';

interface CompareModalProps {
  models: ModelName[];
  session: Session;
  onClose: () => void;
}

/**
 * Get grid columns class based on number of models
 */
function getGridClass(count: number): string {
  if (count <= 2) return 'grid-cols-2';
  if (count === 3) return 'grid-cols-2 lg:grid-cols-3';
  return 'grid-cols-2 lg:grid-cols-4';
}

/**
 * Get the latest completed iteration index for a model
 */
function getLatestCompletedIndex(session: Session, model: ModelName): number | undefined {
  const column = session.models[model];
  if (!column) return undefined;
  const completed = column.iterations.filter((i) => i.status === 'completed');
  return completed.length > 0 ? completed[completed.length - 1].index : undefined;
}

export const CompareModal: FC<CompareModalProps> = ({ models, session, onClose }) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Track selected iteration index per model (default to latest completed)
  const [selectedIterations, setSelectedIterations] = useState<Record<string, number>>({});

  // Sync selected iterations when models or session change
  useEffect(() => {
    setSelectedIterations((prev) => {
      const next = { ...prev };
      for (const model of models) {
        if (next[model] === undefined) {
          const latest = getLatestCompletedIndex(session, model);
          if (latest !== undefined) {
            next[model] = latest;
          }
        }
      }
      return next;
    });
  }, [models, session]);

  // ESC key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Focus trap: cycle Tab/Shift+Tab within modal
  const handleFocusTrap = useCallback((e: KeyboardEvent) => {
    if (e.key !== 'Tab' || !modalRef.current) return;

    const focusable = modalRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, []);

  useEffect(() => {
    document.addEventListener('keydown', handleFocusTrap);
    return () => document.removeEventListener('keydown', handleFocusTrap);
  }, [handleFocusTrap]);

  // Auto-focus close button on mount
  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleIterationChange = (model: ModelName, iterIndex: number) => {
    setSelectedIterations((prev) => ({ ...prev, [model]: iterIndex }));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      data-testid="compare-backdrop"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        className="relative w-[95vw] max-h-[95vh] bg-white dark:bg-gray-900 rounded-lg overflow-auto p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Compare models side by side"
      >
        {/* Close button */}
        <button
          ref={closeButtonRef}
          onClick={onClose}
          className="absolute top-3 right-3 z-10 w-8 h-8 flex items-center justify-center rounded-full bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors border-none cursor-pointer"
          aria-label="Close comparison"
          tabIndex={0}
        >
          <svg
            className="w-4 h-4 text-gray-600 dark:text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Grid */}
        <div className={`grid ${getGridClass(models.length)} gap-4 mt-8`}>
          {models.map((model) => {
            const column = session.models[model];
            if (!column) return null;

            const completedIterations = column.iterations.filter((i) => i.status === 'completed');
            const fallbackIndex =
              completedIterations.length > 0
                ? completedIterations[completedIterations.length - 1].index
                : undefined;
            const resolvedIndex = selectedIterations[model] ?? fallbackIndex;
            const selectedIteration = column.iterations.find((i) => i.index === resolvedIndex);
            const imageUrl = selectedIteration?.imageUrl;

            return (
              <div
                key={model}
                className="flex flex-col gap-2"
                aria-label={`${MODEL_DISPLAY_NAMES[model]} comparison slot`}
              >
                {/* Model name */}
                <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 text-center">
                  {MODEL_DISPLAY_NAMES[model]}
                </h3>

                {/* Image */}
                <div className="bg-gray-100 dark:bg-gray-800 rounded-md overflow-hidden aspect-square flex items-center justify-center">
                  {imageUrl ? (
                    <img
                      src={imageUrl}
                      alt={`${MODEL_DISPLAY_NAMES[model]} iteration ${resolvedIndex}`}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-sm text-gray-400">No image</span>
                  )}
                </div>

                {/* Iteration picker */}
                {completedIterations.length > 1 && (
                  <select
                    value={resolvedIndex}
                    onChange={(e) => handleIterationChange(model, Number(e.target.value))}
                    className="text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
                    aria-label={`Select iteration for ${MODEL_DISPLAY_NAMES[model]}`}
                  >
                    {completedIterations.map((iter) => (
                      <option key={iter.index} value={iter.index}>
                        Iteration {iter.index}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default CompareModal;
