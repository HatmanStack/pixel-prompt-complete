/**
 * AdminUserDetail - User detail slide-over panel.
 * Shows full user record with suspend/unsuspend and notification actions.
 */

import { useState, useEffect, useCallback, type FC } from 'react';
import { useAdminStore } from '@/stores/useAdminStore';
import type { AdminUser } from '@/api/adminClient';

interface Props {
  user: AdminUser;
  onClose: () => void;
}

export const AdminUserDetail: FC<Props> = ({ user, onClose }) => {
  const { suspendUser, unsuspendUser, notifyUser } = useAdminStore();
  const [showNotifyForm, setShowNotifyForm] = useState(false);
  const [notifyType, setNotifyType] = useState('warning');
  const [notifySubject, setNotifySubject] = useState('');
  const [notifyMessage, setNotifyMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [confirmSuspend, setConfirmSuspend] = useState(false);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleSuspend = async () => {
    if (!confirmSuspend) {
      setConfirmSuspend(true);
      return;
    }
    await suspendUser(user.userId, 'Admin action');
    setConfirmSuspend(false);
    onClose();
  };

  const handleUnsuspend = async () => {
    await unsuspendUser(user.userId);
    onClose();
  };

  const handleNotify = async () => {
    if (!notifyMessage.trim()) return;
    setSending(true);
    try {
      await notifyUser(
        user.userId,
        notifyType,
        notifyMessage.trim(),
        notifySubject.trim() || undefined,
      );
      setShowNotifyForm(false);
      setNotifyMessage('');
      setNotifySubject('');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-label="User Detail">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-md bg-gray-900 p-6 overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold">User Detail</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl"
            aria-label="Close"
          >
            x
          </button>
        </div>

        <dl className="space-y-3 mb-6">
          <div>
            <dt className="text-sm text-gray-400">User ID</dt>
            <dd className="font-mono text-sm">{user.userId}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-400">Email</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-400">Tier</dt>
            <dd className="capitalize">{user.tier}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-400">Status</dt>
            <dd>
              <span
                className={`px-2 py-0.5 rounded text-xs ${user.isSuspended ? 'bg-red-900 text-red-300' : 'bg-green-900 text-green-300'}`}
              >
                {user.isSuspended ? 'Suspended' : 'Active'}
              </span>
            </dd>
          </div>
          {user.generateCount !== undefined && (
            <div>
              <dt className="text-sm text-gray-400">Generate Count</dt>
              <dd>{user.generateCount}</dd>
            </div>
          )}
          {user.refineCount !== undefined && (
            <div>
              <dt className="text-sm text-gray-400">Refine Count</dt>
              <dd>{user.refineCount}</dd>
            </div>
          )}
          {user.subscriptionStatus && (
            <div>
              <dt className="text-sm text-gray-400">Subscription Status</dt>
              <dd className="capitalize">{user.subscriptionStatus}</dd>
            </div>
          )}
          {user.createdAt && (
            <div>
              <dt className="text-sm text-gray-400">Created</dt>
              <dd>{new Date(user.createdAt * 1000).toLocaleString()}</dd>
            </div>
          )}
        </dl>

        {/* Actions */}
        <div className="flex flex-col gap-3">
          {user.isSuspended ? (
            <button
              onClick={handleUnsuspend}
              className="px-4 py-2 bg-green-700 text-white rounded hover:bg-green-600"
            >
              Unsuspend User
            </button>
          ) : (
            <button
              onClick={handleSuspend}
              className={`px-4 py-2 rounded text-white ${confirmSuspend ? 'bg-red-600 hover:bg-red-500' : 'bg-red-800 hover:bg-red-700'}`}
            >
              {confirmSuspend ? 'Confirm Suspend' : 'Suspend User'}
            </button>
          )}

          <button
            onClick={() => setShowNotifyForm(!showNotifyForm)}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
          >
            Send Notification
          </button>

          {showNotifyForm && (
            <div className="bg-gray-800 rounded p-4 space-y-3">
              <select
                value={notifyType}
                onChange={(e) => setNotifyType(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
              >
                <option value="warning">Warning</option>
                <option value="suspension">Suspension Notice</option>
                <option value="custom">Custom</option>
              </select>
              {notifyType === 'custom' && (
                <input
                  type="text"
                  value={notifySubject}
                  onChange={(e) => setNotifySubject(e.target.value)}
                  placeholder="Subject"
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                />
              )}
              <textarea
                value={notifyMessage}
                onChange={(e) => setNotifyMessage(e.target.value)}
                rows={3}
                placeholder="Message"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white resize-y"
              />
              <button
                onClick={handleNotify}
                disabled={sending || !notifyMessage.trim()}
                className="px-4 py-2 bg-accent text-white rounded hover:bg-accent/80 disabled:opacity-50"
              >
                {sending ? 'Sending...' : 'Send'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
