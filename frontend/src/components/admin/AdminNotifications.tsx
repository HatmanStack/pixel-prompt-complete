/**
 * AdminNotifications section.
 * Provides a form to send notifications to users and shows recent notifications.
 */

import { useState, type FC } from 'react';
import { useAdminStore } from '@/stores/useAdminStore';

export const AdminNotifications: FC = () => {
  const { notifyUser } = useAdminStore();
  const [userId, setUserId] = useState('');
  const [type, setType] = useState('warning');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleSend = async () => {
    if (!userId.trim() || !message.trim()) return;
    setSending(true);
    setResult(null);
    try {
      await notifyUser(userId.trim(), type, message.trim(), subject.trim() || undefined);
      setResult('Notification sent successfully');
      setMessage('');
      setSubject('');
    } catch {
      setResult('Failed to send notification');
    } finally {
      setSending(false);
    }
  };

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Notifications</h2>

      <div className="bg-gray-800 rounded-lg p-6 max-w-xl">
        <h3 className="text-lg font-medium mb-4">Send Notification</h3>

        <div className="flex flex-col gap-4">
          <div>
            <label htmlFor="notify-user-id" className="block text-sm text-gray-400 mb-1">
              User ID
            </label>
            <input
              id="notify-user-id"
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
              placeholder="Enter user ID"
            />
          </div>

          <div>
            <label htmlFor="notify-type" className="block text-sm text-gray-400 mb-1">
              Type
            </label>
            <select
              id="notify-type"
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
            >
              <option value="warning">Warning</option>
              <option value="suspension">Suspension Notice</option>
              <option value="custom">Custom</option>
            </select>
          </div>

          {type === 'custom' && (
            <div>
              <label htmlFor="notify-subject" className="block text-sm text-gray-400 mb-1">
                Subject
              </label>
              <input
                id="notify-subject"
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                placeholder="Email subject"
              />
            </div>
          )}

          <div>
            <label htmlFor="notify-message" className="block text-sm text-gray-400 mb-1">
              Message
            </label>
            <textarea
              id="notify-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white resize-y"
              placeholder="Enter notification message"
            />
          </div>

          <button
            onClick={handleSend}
            disabled={sending || !userId.trim() || !message.trim()}
            className="px-4 py-2 bg-accent text-white rounded hover:bg-accent/80 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {sending ? 'Sending...' : 'Send Notification'}
          </button>

          {result && (
            <p
              className={`text-sm ${result.includes('success') ? 'text-green-400' : 'text-red-400'}`}
            >
              {result}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
