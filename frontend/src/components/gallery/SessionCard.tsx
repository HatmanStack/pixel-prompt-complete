/**
 * SessionCard Component
 * Displays a session preview card in the gallery
 */

import type { FC } from 'react';
import type { SessionPreview } from '@/types';

interface SessionCardProps {
  session: SessionPreview;
  onClick: () => void;
}

/**
 * Format date for display
 */
function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  } catch {
    return dateStr;
  }
}

export const SessionCard: FC<SessionCardProps> = ({ session, onClick }) => {
  return (
    <div
      className="
        p-3 border rounded-lg cursor-pointer
        border-gray-200 dark:border-gray-700
        bg-white dark:bg-gray-800
        hover:border-accent hover:shadow-md
        transition-all duration-200
        focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
      "
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      aria-label={`View session: ${session.prompt}`}
    >
      {/* Thumbnail */}
      {session.thumbnail ? (
        <img
          src={session.thumbnail}
          alt={session.prompt}
          className="w-full aspect-video object-cover rounded"
          loading="lazy"
        />
      ) : (
        <div className="w-full aspect-video bg-gray-100 dark:bg-gray-700 rounded flex items-center justify-center">
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
      )}

      {/* Info */}
      <p className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
        {session.prompt}
      </p>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {session.totalIterations} iteration{session.totalIterations !== 1 ? 's' : ''}{' '}
        · {formatDate(session.createdAt)}
      </p>
    </div>
  );
};

export default SessionCard;
