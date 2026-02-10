/**
 * IterationCard Component
 * Displays a single iteration with image, status, and metadata
 */

import { memo, type FC } from 'react';
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton';
import type { ModelName, Iteration } from '@/types';
import { MODEL_DISPLAY_NAMES } from '@/types';

interface IterationCardProps {
  model: ModelName;
  iteration: Iteration;
  onExpand?: () => void;
}

/**
 * Status badge component
 */
const StatusBadge: FC<{ status: Iteration['status'] }> = ({ status }) => {
  const statusStyles: Record<Iteration['status'], string> = {
    pending: 'bg-gray-500 text-white',
    loading: 'bg-blue-500 text-white animate-pulse',
    in_progress: 'bg-blue-500 text-white animate-pulse',
    completed: 'bg-green-500 text-white',
    error: 'bg-red-500 text-white',
    disabled: 'bg-gray-400 text-white',
    partial: 'bg-yellow-500 text-white',
  };

  const statusLabels: Record<Iteration['status'], string> = {
    pending: 'Pending',
    loading: 'Generating...',
    in_progress: 'Generating...',
    completed: 'Done',
    error: 'Error',
    disabled: 'Disabled',
    partial: 'Partial',
  };

  return (
    <span
      className={`px-2 py-0.5 text-xs font-medium rounded-full ${statusStyles[status]}`}
    >
      {statusLabels[status]}
    </span>
  );
};

/**
 * Error state display
 */
const ErrorState: FC<{ error?: string }> = ({ error }) => (
  <div className="w-full aspect-square bg-red-50 dark:bg-red-900/20 flex flex-col items-center justify-center p-4">
    <svg
      className="w-8 h-8 text-red-500 mb-2"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
      />
    </svg>
    <p className="text-sm text-red-600 dark:text-red-400 text-center">
      {error || 'Generation failed'}
    </p>
  </div>
);

/**
 * Pending placeholder
 */
const PendingPlaceholder: FC = () => (
  <div className="w-full aspect-square bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
    <svg
      className="w-8 h-8 text-gray-400"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
      />
    </svg>
  </div>
);

/**
 * Truncate text to specified length
 */
function truncate(text: string, length: number): string {
  if (text.length <= length) return text;
  return text.slice(0, length - 3) + '...';
}

export const IterationCard: FC<IterationCardProps> = memo(({
  model,
  iteration,
  onExpand,
}) => {
  const isClickable = iteration.status === 'completed' && iteration.imageUrl;

  return (
    <div
      className={`
        relative rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700
        bg-white dark:bg-gray-800 shadow-sm
        ${isClickable ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}
      `}
      onClick={isClickable ? onExpand : undefined}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onExpand?.();
              }
            }
          : undefined
      }
      aria-label={
        isClickable
          ? `View ${MODEL_DISPLAY_NAMES[model]} iteration ${iteration.index}`
          : undefined
      }
    >
      {/* Status indicator badge */}
      <div className="absolute top-2 left-2 z-10">
        <StatusBadge status={iteration.status} />
      </div>

      {/* Image or placeholder */}
      {iteration.status === 'completed' && iteration.imageUrl ? (
        <img
          src={iteration.imageUrl}
          alt={`${MODEL_DISPLAY_NAMES[model]} iteration ${iteration.index}`}
          className="w-full aspect-square object-cover"
          loading="lazy"
        />
      ) : iteration.status === 'loading' ? (
        <LoadingSkeleton width="100%" height="auto" className="aspect-square" />
      ) : iteration.status === 'error' ? (
        <ErrorState error={iteration.error} />
      ) : (
        <PendingPlaceholder />
      )}

      {/* Iteration number and prompt preview */}
      <div className="p-2 bg-gray-50 dark:bg-gray-900">
        <span className="text-xs text-gray-500 dark:text-gray-400 block">
          #{iteration.index}: {truncate(iteration.prompt, 50)}
        </span>
      </div>
    </div>
  );
});

export default IterationCard;
