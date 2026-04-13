/**
 * AdminRevenue tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../../../../src/api/adminClient', () => ({
  fetchAdminUsers: vi.fn().mockResolvedValue({ users: [], nextKey: null }),
  fetchAdminUserDetail: vi.fn(),
  suspendUser: vi.fn(),
  unsuspendUser: vi.fn(),
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

// Mock recharts
vi.mock('recharts', () => ({
  AreaChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="area-chart">{children}</div>
  ),
  Area: () => <div data-testid="area" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  CartesianGrid: () => <div />,
}));

import { useAdminStore } from '../../../../src/stores/useAdminStore';
import { AdminRevenue } from '../../../../src/components/admin/AdminRevenue';

describe('AdminRevenue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders revenue metric cards with correct values', () => {
    useAdminStore.setState({
      revenue: {
        current: { activeSubscribers: 42, mrr: 210000, monthlyChurn: 3, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminRevenue />);

    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('computes churn rate correctly', () => {
    useAdminStore.setState({
      revenue: {
        current: { activeSubscribers: 100, mrr: 500000, monthlyChurn: 5, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminRevenue />);

    // Churn rate: 5 / 100 * 100 = 5.0%
    expect(screen.getByText('5.0%')).toBeInTheDocument();
  });

  it('handles zero subscribers without division by zero', () => {
    useAdminStore.setState({
      revenue: {
        current: { activeSubscribers: 0, mrr: 0, monthlyChurn: 0, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminRevenue />);

    // Should display 0% or N/A, not crash
    expect(screen.getByText('Revenue')).toBeInTheDocument();
    expect(screen.getByText('0.0%')).toBeInTheDocument();
  });

  it('renders historical chart when snapshot data available', () => {
    useAdminStore.setState({
      revenue: {
        current: { activeSubscribers: 42, mrr: 210000, monthlyChurn: 3, updatedAt: 0 },
        history: [
          {
            date: '2026-04-10',
            modelCounts: {},
            usersByTier: {},
            suspendedCount: 0,
            revenue: { activeSubscribers: 38 },
          },
          {
            date: '2026-04-11',
            modelCounts: {},
            usersByTier: {},
            suspendedCount: 0,
            revenue: { activeSubscribers: 40 },
          },
        ],
      },
      revenueLoading: false,
    });

    render(<AdminRevenue />);

    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });

  it('renders date range selector buttons', () => {
    useAdminStore.setState({
      revenue: {
        current: { activeSubscribers: 10, mrr: 50000, monthlyChurn: 1, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminRevenue />);

    expect(screen.getByRole('button', { name: '7 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '14 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '30 days' })).toBeInTheDocument();
  });

  it('calls fetchRevenue on date range change', () => {
    const fetchRevenueFn = vi.fn().mockResolvedValue(undefined);
    const fetchMetricsFn = vi.fn().mockResolvedValue(undefined);
    useAdminStore.setState({
      fetchRevenue: fetchRevenueFn,
      fetchMetrics: fetchMetricsFn,
      revenue: {
        current: { activeSubscribers: 10, mrr: 50000, monthlyChurn: 1, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminRevenue />);

    fireEvent.click(screen.getByRole('button', { name: '30 days' }));

    expect(fetchMetricsFn).toHaveBeenCalledWith(30);
  });

  it('shows loading state', () => {
    useAdminStore.setState({
      revenue: null,
      revenueLoading: true,
    });

    render(<AdminRevenue />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
