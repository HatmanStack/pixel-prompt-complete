/**
 * Admin page tests.
 *
 * This page is the client-side gate on the admin dashboard. It is not the
 * security boundary (the API enforces the admin group), but it decides who
 * sees the surface, and it was untested.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const mockFetchMe = vi.fn();
const mockIsAuthenticated = vi.fn();

vi.mock('../../../src/api/me', () => ({
  fetchMe: () => mockFetchMe(),
}));

vi.mock('../../../src/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: { isAuthenticated: () => boolean }) => unknown) =>
    selector({ isAuthenticated: mockIsAuthenticated }),
}));

vi.mock('../../../src/components/admin/AdminLayout', () => ({
  AdminLayout: () => <div data-testid="admin-layout" />,
}));

import { Admin } from '../../../src/pages/Admin';

describe('Admin page', () => {
  beforeEach(() => {
    mockFetchMe.mockReset();
    mockIsAuthenticated.mockReset();
    mockIsAuthenticated.mockReturnValue(true);
    mockFetchMe.mockResolvedValue({ groups: ['admins'] });
  });

  it('renders the dashboard for a member of admins', async () => {
    render(<Admin />);
    expect(await screen.findByTestId('admin-layout')).toBeInTheDocument();
  });

  it('denies a signed-in user who is not in admins', async () => {
    mockFetchMe.mockResolvedValue({ groups: ['users'] });
    render(<Admin />);

    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });

  it('denies an anonymous visitor without calling the API', async () => {
    mockIsAuthenticated.mockReturnValue(false);
    render(<Admin />);

    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(mockFetchMe).not.toHaveBeenCalled();
  });

  it('denies access when the group lookup fails', async () => {
    // Failing open here would show the dashboard to anyone whenever /me
    // is unavailable.
    mockFetchMe.mockRejectedValue(new Error('me endpoint down'));
    render(<Admin />);

    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });

  it('denies access when groups is missing or malformed', async () => {
    mockFetchMe.mockResolvedValue({});
    render(<Admin />);
    expect(await screen.findByText('Access denied')).toBeInTheDocument();
  });

  it('shows progress while the check is in flight', () => {
    mockFetchMe.mockReturnValue(new Promise(() => {}));
    render(<Admin />);
    expect(screen.getByText(/Checking admin access/)).toBeInTheDocument();
  });

  it('does not flash the dashboard before the check resolves', () => {
    mockFetchMe.mockReturnValue(new Promise(() => {}));
    render(<Admin />);
    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });

  it('ignores a resolution that lands after unmount', async () => {
    let resolve!: (v: unknown) => void;
    mockFetchMe.mockReturnValue(new Promise((r) => (resolve = r)));
    const { unmount } = render(<Admin />);
    unmount();
    resolve({ groups: ['admins'] });
    await waitFor(() => expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument());
  });
});
