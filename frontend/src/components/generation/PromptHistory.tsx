/**
 * PromptHistory Component
 * Shows prompt history (authenticated) and recent feed (all users)
 */

import { useState, useEffect, useCallback, useRef, type FC } from 'react';
import { getRecentPrompts, getPromptHistory } from '@/api/client';
import { useAuthStore } from '@/stores/useAuthStore';
import { useAppStore } from '@/stores/useAppStore';
import type { PromptHistoryItem } from '@/types';

/**
 * Format a timestamp as relative time (e.g., "2h ago")
 */
function formatRelativeTime(epochSeconds: number): string {
  const diff = Date.now() - epochSeconds * 1000;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Truncate text
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

interface PromptListProps {
  items: PromptHistoryItem[];
  isLoading: boolean;
  onSelect: (prompt: string) => void;
}

const PromptList: FC<PromptListProps> = ({ items, isLoading, onSelect }) => {
  if (isLoading) {
    return (
      <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-3">Loading...</div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-3">
        No prompts yet
      </div>
    );
  }

  return (
    <ul className="space-y-1 max-h-48 overflow-y-auto">
      {items.map((item) => (
        <li key={`${item.sessionId}-${item.createdAt}`}>
          <button
            onClick={() => onSelect(item.prompt)}
            className="w-full text-left px-2 py-1.5 rounded text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors bg-transparent border-none cursor-pointer"
          >
            <span className="text-gray-700 dark:text-gray-300 block">
              {truncateText(item.prompt, 80)}
            </span>
            <span className="text-gray-400 dark:text-gray-500 text-[10px]">
              {formatRelativeTime(item.createdAt)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
};

export const PromptHistory: FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'recent' | 'history'>('recent');
  const [recentItems, setRecentItems] = useState<PromptHistoryItem[]>([]);
  const [historyItems, setHistoryItems] = useState<PromptHistoryItem[]>([]);
  const [isLoadingRecent, setIsLoadingRecent] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());

  const handleSelect = useCallback((prompt: string) => {
    useAppStore.getState().setPrompt(prompt);
  }, []);

  // Fetch recent prompts when tab is active and panel is open
  useEffect(() => {
    if (!isOpen || activeTab !== 'recent') return;
    let ignore = false;
    setIsLoadingRecent(true);
    getRecentPrompts(20)
      .then((res) => {
        if (!ignore) setRecentItems(res.prompts);
      })
      .catch((err) => {
        if (!ignore) console.error('Failed to fetch recent prompts:', err);
      })
      .finally(() => {
        if (!ignore) setIsLoadingRecent(false);
      });
    return () => {
      ignore = true;
    };
  }, [isOpen, activeTab]);

  // Fetch history when tab is active and panel is open
  useEffect(() => {
    if (!isOpen || activeTab !== 'history' || !isAuthenticated) return;
    let ignore = false;
    setIsLoadingHistory(true);
    getPromptHistory(20, searchQuery || undefined)
      .then((res) => {
        if (!ignore) setHistoryItems(res.prompts);
      })
      .catch((err) => {
        if (!ignore) console.error('Failed to fetch prompt history:', err);
      })
      .finally(() => {
        if (!ignore) setIsLoadingHistory(false);
      });
    return () => {
      ignore = true;
    };
  }, [isOpen, activeTab, isAuthenticated, searchQuery]);

  // Clean up debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // Debounced search handler
  const handleSearchChange = (value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setSearchQuery(value);
    }, 300);
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors border-none cursor-pointer"
      >
        <span>Prompt History</span>
        <svg
          className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="p-3">
          {/* Tabs */}
          <div className="flex gap-2 mb-3">
            <button
              type="button"
              onClick={() => setActiveTab('recent')}
              className={`text-xs px-2 py-1 rounded border-none cursor-pointer transition-colors ${
                activeTab === 'recent'
                  ? 'bg-accent text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            >
              Recent
            </button>
            {isAuthenticated && (
              <button
                type="button"
                onClick={() => setActiveTab('history')}
                className={`text-xs px-2 py-1 rounded border-none cursor-pointer transition-colors ${
                  activeTab === 'history'
                    ? 'bg-accent text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                My History
              </button>
            )}
          </div>

          {/* Search (history tab only) */}
          {activeTab === 'history' && isAuthenticated && (
            <input
              type="text"
              placeholder="Search prompts..."
              aria-label="Search prompts"
              onChange={(e) => handleSearchChange(e.target.value)}
              className="w-full px-2 py-1 mb-2 text-xs border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
            />
          )}

          {/* Content */}
          {activeTab === 'recent' && (
            <PromptList items={recentItems} isLoading={isLoadingRecent} onSelect={handleSelect} />
          )}
          {activeTab === 'history' && isAuthenticated && (
            <PromptList items={historyItems} isLoading={isLoadingHistory} onSelect={handleSelect} />
          )}
        </div>
      )}
    </div>
  );
};

export default PromptHistory;
