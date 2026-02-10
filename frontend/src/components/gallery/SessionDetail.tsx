/**
 * SessionDetail Component
 * Modal view showing all model columns for a session from gallery
 */

import { useEffect, useState, type FC } from 'react';
import { getSessionStatus } from '@/api/client';
import { ModelColumn } from '@/components/generation/ModelColumn';
import { ImageModal } from '@/components/features/generation/ImageModal';
import Modal from '@/components/common/Modal';
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton';
import type { Session, ModelName, Iteration, ModelColumn as ModelColumnType } from '@/types';
import { MODELS } from '@/types';

interface SessionDetailProps {
  sessionId: string;
  onClose: () => void;
}

/**
 * Create empty column for display
 */
function createEmptyColumn(model: ModelName): ModelColumnType {
  return {
    name: model,
    enabled: false,
    status: 'pending',
    iterations: [],
  };
}

export const SessionDetail: FC<SessionDetailProps> = ({ sessionId, onClose }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedImage, setExpandedImage] = useState<{
    model: ModelName;
    iteration: Iteration;
  } | null>(null);

  // Fetch session data
  useEffect(() => {
    let mounted = true;

    async function fetchSession() {
      try {
        setLoading(true);
        setError(null);
        const session = await getSessionStatus(sessionId);
        if (mounted) {
          setSession(session);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load session');
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    fetchSession();

    return () => {
      mounted = false;
    };
  }, [sessionId]);

  // Handle image expansion
  const handleImageExpand = (model: ModelName, iteration: Iteration) => {
    if (iteration.status === 'completed' && iteration.imageUrl) {
      setExpandedImage({ model, iteration });
    }
  };

  // Loading state
  if (loading) {
    return (
      <Modal isOpen onClose={onClose} ariaLabel="Loading session details">
        <div className="flex flex-col gap-4 p-4 min-w-[300px]">
          <LoadingSkeleton height={24} width={200} />
          <div className="flex gap-4 overflow-x-auto">
            {MODELS.map((model) => (
              <div key={model} className="min-w-[250px]">
                <LoadingSkeleton height={300} />
              </div>
            ))}
          </div>
        </div>
      </Modal>
    );
  }

  // Error state
  if (error) {
    return (
      <Modal isOpen onClose={onClose} ariaLabel="Error loading session">
        <div className="flex flex-col items-center gap-4 p-8 text-center">
          <span className="text-4xl">⚠</span>
          <p className="text-lg font-semibold text-red-600 dark:text-red-400">{error}</p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-accent text-white rounded hover:bg-accent/90"
          >
            Close
          </button>
        </div>
      </Modal>
    );
  }

  // Session not found
  if (!session) {
    return (
      <Modal isOpen onClose={onClose} ariaLabel="Session not found">
        <div className="flex flex-col items-center gap-4 p-8 text-center">
          <span className="text-4xl">🔍</span>
          <p className="text-lg font-semibold">Session not found</p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-accent text-white rounded hover:bg-accent/90"
          >
            Close
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <>
      <Modal isOpen onClose={onClose} ariaLabel={`Session: ${session.prompt}`}>
        <div className="flex flex-col gap-4 max-w-[95vw] max-h-[90vh]">
          {/* Header */}
          <div className="flex flex-col gap-2 p-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              {session.prompt}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Created: {new Date(session.createdAt).toLocaleString()}
            </p>
          </div>

          {/* Model columns */}
          <div className="flex gap-4 overflow-x-auto p-4">
            {MODELS.map((model) => {
              const column = session.models[model] ?? createEmptyColumn(model);
              return (
                <ModelColumn
                  key={model}
                  model={model}
                  column={column}
                  isSelected={false}
                  onToggleSelect={() => {}}
                  onImageExpand={handleImageExpand}
                />
              );
            })}
          </div>

          {/* Close button */}
          <div className="flex justify-end p-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={onClose}
              className="px-6 py-2 bg-accent text-white rounded hover:bg-accent/90 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </Modal>

      {/* Image modal */}
      {expandedImage && (
        <ImageModal
          isOpen={!!expandedImage}
          onClose={() => setExpandedImage(null)}
          imageUrl={expandedImage.iteration.imageUrl || ''}
          model={expandedImage.model}
          iteration={expandedImage.iteration}
        />
      )}
    </>
  );
};

export default SessionDetail;
