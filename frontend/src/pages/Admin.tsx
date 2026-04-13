/**
 * Admin page.
 * Checks admin group membership via /me response and renders the AdminLayout.
 * Non-admin users see an "Access denied" message.
 */

import { useEffect, useState, type FC } from 'react';
import { fetchMe } from '@/api/me';
import { useAuthStore } from '@/stores/useAuthStore';
import { AdminLayout } from '@/components/admin/AdminLayout';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';

export const Admin: FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated) {
      setIsAdmin(false);
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMe();
        if (cancelled) return;
        setIsAdmin(Array.isArray(me.groups) && me.groups.includes('admins'));
      } catch {
        if (cancelled) return;
        setIsAdmin(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-primary">
        <LoadingSpinner size="lg" message="Checking admin access..." />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 text-center bg-primary text-white">
        <div>
          <h1 className="text-2xl font-semibold mb-2">Access denied</h1>
          <p className="text-sm text-gray-400 mb-4">
            You do not have permission to view this page.
          </p>
          <a href="/" className="underline text-accent">
            Return home
          </a>
        </div>
      </div>
    );
  }

  return <AdminLayout />;
};

export default Admin;
