/**
 * AdminLayout tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../../src/api/adminClient', () => ({
  fetchAdminUsers: vi.fn().mockResolvedValue({ users: [], nextKey: null }),
  fetchAdminModels: vi.fn().mockResolvedValue({ models: [] }),
  fetchAdminMetrics: vi.fn().mockResolvedValue({ today: null, history: [] }),
  fetchAdminRevenue: vi.fn().mockResolvedValue({
    current: { activeSubscribers: 0, mrr: 0, monthlyChurn: 0, updatedAt: 0 },
    history: [],
  }),
  fetchAdminUserDetail: vi.fn(),
  suspendUser: vi.fn(),
  unsuspendUser: vi.fn(),
  notifyUser: vi.fn(),
  disableModel: vi.fn(),
  enableModel: vi.fn(),
}));

import { AdminLayout } from '../../../../src/components/admin/AdminLayout';

describe('AdminLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all 5 navigation items', () => {
    render(<AdminLayout />);

    const nav = screen.getByRole('navigation');
    const buttons = nav.querySelectorAll('button');
    const labels = Array.from(buttons).map((b) => b.textContent?.trim());

    expect(labels).toContain('Overview');
    expect(labels).toContain('Users');
    expect(labels).toContain('Models');
    expect(labels).toContain('Notifications');
    expect(labels).toContain('Revenue');
    expect(buttons).toHaveLength(5);
  });

  it('switches active section when clicking a nav item', async () => {
    const user = userEvent.setup();
    render(<AdminLayout />);

    // Default section is Overview
    expect(screen.getByRole('heading', { name: /overview/i })).toBeInTheDocument();

    // Click Users nav
    await user.click(screen.getByText('Users'));
    expect(screen.getByRole('heading', { name: /users/i })).toBeInTheDocument();

    // Click Models nav
    await user.click(screen.getByText('Models'));
    expect(screen.getByRole('heading', { name: /models/i })).toBeInTheDocument();

    // Click Revenue nav
    await user.click(screen.getByText('Revenue'));
    expect(screen.getByRole('heading', { name: /revenue/i })).toBeInTheDocument();
  });

  it('renders the admin dashboard heading', () => {
    render(<AdminLayout />);

    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument();
  });
});
