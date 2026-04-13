/**
 * AdminUsers tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../../src/api/adminClient', () => ({
  fetchAdminUsers: vi.fn(),
  fetchAdminUserDetail: vi.fn(),
  suspendUser: vi.fn().mockResolvedValue(undefined),
  unsuspendUser: vi.fn().mockResolvedValue(undefined),
  notifyUser: vi.fn(),
  fetchAdminModels: vi.fn().mockResolvedValue({ models: [] }),
  disableModel: vi.fn(),
  enableModel: vi.fn(),
  fetchAdminMetrics: vi.fn().mockResolvedValue({ today: null, history: [] }),
  fetchAdminRevenue: vi.fn().mockResolvedValue({
    current: { activeSubscribers: 0, mrr: 0, monthlyChurn: 0, updatedAt: 0 },
    history: [],
  }),
}));

import { useAdminStore } from '../../../../src/stores/useAdminStore';
import { AdminUsers } from '../../../../src/components/admin/AdminUsers';
import { fetchAdminUsers, suspendUser } from '../../../../src/api/adminClient';

const sampleUsers = [
  {
    userId: 'u1',
    email: 'alice@example.com',
    tier: 'free',
    isSuspended: false,
    generateCount: 5,
    refineCount: 10,
    createdAt: 1712000000,
  },
  {
    userId: 'u2',
    email: 'bob@example.com',
    tier: 'paid',
    isSuspended: true,
    generateCount: 20,
    refineCount: 50,
    createdAt: 1713000000,
  },
  {
    userId: 'u3',
    email: 'carol@example.com',
    tier: 'free',
    isSuspended: false,
    generateCount: 1,
    refineCount: 0,
    createdAt: 1714000000,
  },
];

describe('AdminUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock returns sample users on every call (including the useEffect fetch)
    vi.mocked(fetchAdminUsers).mockResolvedValue({ users: sampleUsers, nextKey: null });
    vi.mocked(suspendUser).mockResolvedValue(undefined);
    // Pre-populate store state
    useAdminStore.setState({
      users: sampleUsers,
      usersLoading: false,
      usersNextKey: null,
      selectedUser: null,
      userDetailLoading: false,
      tierFilter: null,
      suspendedFilter: null,
      searchQuery: '',
      requestEpoch: 0,
    });
  });

  it('renders user table with all users', () => {
    render(<AdminUsers />);

    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    expect(screen.getByText('carol@example.com')).toBeInTheDocument();
  });

  it('filters users by search query on client side', async () => {
    const user = userEvent.setup();
    render(<AdminUsers />);

    // All users visible initially
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText(/search/i);
    await user.type(searchInput, 'alice');

    // Only alice should be visible now
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.queryByText('bob@example.com')).not.toBeInTheDocument();
    expect(screen.queryByText('carol@example.com')).not.toBeInTheDocument();
  });

  it('shows suspend button for active users', () => {
    render(<AdminUsers />);

    const suspendButtons = screen.getAllByRole('button', { name: /^suspend$/i });
    // alice and carol are active
    expect(suspendButtons).toHaveLength(2);
  });

  it('shows unsuspend button for suspended users', () => {
    render(<AdminUsers />);

    const unsuspendButtons = screen.getAllByRole('button', { name: /unsuspend/i });
    // bob is suspended
    expect(unsuspendButtons).toHaveLength(1);
  });

  it('shows load more button when usersNextKey is present', async () => {
    vi.mocked(fetchAdminUsers).mockResolvedValue({ users: sampleUsers, nextKey: 'next123' });
    useAdminStore.setState({ usersNextKey: 'next123' });

    render(<AdminUsers />);

    // Wait for the button to appear after useEffect fetch returns with nextKey
    expect(await screen.findByRole('button', { name: /load more/i })).toBeInTheDocument();
  });

  it('does not show load more button when usersNextKey is null', () => {
    useAdminStore.setState({ usersNextKey: null });

    render(<AdminUsers />);

    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
  });

  it('opens user detail panel when clicking a user row', async () => {
    const user = userEvent.setup();
    render(<AdminUsers />);

    const row = screen.getByText('alice@example.com').closest('tr');
    expect(row).toBeTruthy();
    await user.click(row!);

    // Detail panel should appear
    expect(screen.getByText(/user detail/i)).toBeInTheDocument();
  });

  it('calls suspend API when suspend button is clicked', async () => {
    const user = userEvent.setup();
    render(<AdminUsers />);

    const suspendButtons = screen.getAllByRole('button', { name: /^suspend$/i });
    await user.click(suspendButtons[0]);

    expect(suspendUser).toHaveBeenCalledWith('u1', 'Admin action');
  });
});
