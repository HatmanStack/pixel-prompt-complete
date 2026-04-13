/**
 * AdminUsers - User management section.
 * Searchable table with tier/suspension filters, pagination, and action buttons.
 */

import { useEffect, useState, useMemo, type FC } from 'react';
import { useAdminStore } from '@/stores/useAdminStore';
import { AdminUserDetail } from './AdminUserDetail';
import type { AdminUser } from '@/api/adminClient';

export const AdminUsers: FC = () => {
  const {
    users,
    usersLoading,
    usersNextKey,
    fetchUsers,
    suspendUser,
    unsuspendUser,
    setTierFilter,
    setSuspendedFilter,
    tierFilter,
    suspendedFilter,
  } = useAdminStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  useEffect(() => {
    fetchUsers(true);
  }, [fetchUsers, tierFilter, suspendedFilter]);

  const filteredUsers = useMemo(() => {
    if (!searchQuery.trim()) return users;
    const q = searchQuery.toLowerCase();
    return users.filter(
      (u) => u.email?.toLowerCase().includes(q) || u.userId?.toLowerCase().includes(q),
    );
  }, [users, searchQuery]);

  const handleLoadMore = () => {
    fetchUsers(false);
  };

  const handleSuspend = async (e: React.MouseEvent, userId: string) => {
    e.stopPropagation();
    await suspendUser(userId, 'Admin action');
  };

  const handleUnsuspend = async (e: React.MouseEvent, userId: string) => {
    e.stopPropagation();
    await unsuspendUser(userId);
  };

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Users</h2>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search by email or user ID"
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
        />
        <select
          value={tierFilter ?? ''}
          onChange={(e) => setTierFilter(e.target.value || null)}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
        >
          <option value="">All Tiers</option>
          <option value="free">Free</option>
          <option value="paid">Paid</option>
        </select>
        <select
          value={suspendedFilter === null ? '' : suspendedFilter ? 'yes' : 'no'}
          onChange={(e) => {
            const v = e.target.value;
            setSuspendedFilter(v === '' ? null : v === 'yes');
          }}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
        >
          <option value="">All Status</option>
          <option value="yes">Suspended</option>
          <option value="no">Active</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-700">
              <th className="pb-2 pr-4">Email</th>
              <th className="pb-2 pr-4">Tier</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Generates</th>
              <th className="pb-2 pr-4">Refines</th>
              <th className="pb-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user) => (
              <tr
                key={user.userId}
                className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
                onClick={() => setSelectedUser(user)}
              >
                <td className="py-2 pr-4">{user.email}</td>
                <td className="py-2 pr-4 capitalize">{user.tier}</td>
                <td className="py-2 pr-4">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${user.isSuspended ? 'bg-red-900 text-red-300' : 'bg-green-900 text-green-300'}`}
                  >
                    {user.isSuspended ? 'Suspended' : 'Active'}
                  </span>
                </td>
                <td className="py-2 pr-4">{user.generateCount ?? 0}</td>
                <td className="py-2 pr-4">{user.refineCount ?? 0}</td>
                <td className="py-2">
                  {user.isSuspended ? (
                    <button
                      onClick={(e) => handleUnsuspend(e, user.userId)}
                      className="px-3 py-1 text-xs bg-green-800 text-green-200 rounded hover:bg-green-700"
                    >
                      Unsuspend
                    </button>
                  ) : (
                    <button
                      onClick={(e) => handleSuspend(e, user.userId)}
                      className="px-3 py-1 text-xs bg-red-800 text-red-200 rounded hover:bg-red-700"
                    >
                      Suspend
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {usersLoading && (
        <div className="text-center py-4 text-gray-400 animate-pulse">Loading users...</div>
      )}

      {usersNextKey && !usersLoading && (
        <div className="text-center py-4">
          <button
            onClick={handleLoadMore}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
          >
            Load More
          </button>
        </div>
      )}

      {/* User Detail Panel */}
      {selectedUser && (
        <AdminUserDetail user={selectedUser} onClose={() => setSelectedUser(null)} />
      )}
    </div>
  );
};
