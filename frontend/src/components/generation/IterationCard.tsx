/**
 * IterationCard Component
 * Displays a single iteration with image, status, and metadata
 */

import { memo, useState, type FC } from 'react';
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton';
import { getDownloadUrl } from '@/api/client';
import type { ModelName, Iteration } from '@/types';
import { MODEL_DISPLAY_NAMES } from '@/types';

interface IterationCardProps {
  model: ModelName;
  iteration: Iteration;
  sessionId?: string;
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
    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${statusStyles[status]}`}>
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
    <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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

export const IterationCard: FC<IterationCardProps> = memo(
  ({ model, iteration, sessionId, onExpand }) => {
    const isClickable = iteration.status === 'completed' && iteration.imageUrl;
    const isCompleted = iteration.status === 'completed';
    const [isDownloading, setIsDownloading] = useState(false);
    const [isAdaptedExpanded, setIsAdaptedExpanded] = useState(false);

    const hasAdaptedPrompt =
      !!iteration.adaptedPrompt && iteration.adaptedPrompt !== iteration.prompt;

    const handleDownload = async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!sessionId || isDownloading) return;
      setIsDownloading(true);
      try {
        const { url, filename } = await getDownloadUrl(sessionId, model, iteration.index);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (err) {
        console.error('Download failed:', err);
      } finally {
        setIsDownloading(false);
      }
    };

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
                if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) {
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

        {/* Iteration number, prompt preview, and download */}
        <div className="p-2 bg-gray-50 dark:bg-gray-900">
          <div className="flex items-start justify-between gap-1">
            <span className="text-xs text-gray-500 dark:text-gray-400 block flex-1">
              #{iteration.index}: {truncate(iteration.prompt, 50)}
            </span>
            {isCompleted && sessionId && (
              <button
                onClick={handleDownload}
                disabled={isDownloading}
                className="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                aria-label="Download image"
                title="Download image"
              >
                {isDownloading ? (
                  <svg
                    className="w-3.5 h-3.5 text-gray-400 animate-spin"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                ) : (
                  <svg
                    className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"
                    />
                  </svg>
                )}
              </button>
            )}
          </div>
          {hasAdaptedPrompt && (
            <div className="mt-1">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setIsAdaptedExpanded(!isAdaptedExpanded);
                }}
                className="text-xs text-blue-500 dark:text-blue-400 hover:underline bg-transparent border-none cursor-pointer p-0"
              >
                {isAdaptedExpanded ? 'Hide adapted' : 'Show adapted'}
              </button>
              {isAdaptedExpanded && (
                <p className="text-xs text-gray-400 dark:text-gray-500 italic mt-1 break-words">
                  {iteration.adaptedPrompt}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    );
  },
);

export default IterationCard;
