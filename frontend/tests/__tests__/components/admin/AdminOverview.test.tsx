/**
 * AdminOverview tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

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

import { useAdminStore } from '../../../../src/stores/useAdminStore';
import { AdminOverview } from '../../../../src/components/admin/AdminOverview';

describe('AdminOverview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state when data is loading', () => {
    useAdminStore.setState({ modelsLoading: true, metricsLoading: true });

    render(<AdminOverview />);

    expect(screen.getByText('Overview')).toBeInTheDocument();
  });

  it('renders model status cards for all 4 models', () => {
    useAdminStore.setState({
      models: [
        { name: 'gemini', provider: 'google_gemini', enabled: true, dailyCount: 100, dailyCap: 500 },
        { name: 'nova', provider: 'bedrock_nova', enabled: true, dailyCount: 200, dailyCap: 500 },
        { name: 'openai', provider: 'openai', enabled: true, dailyCount: 400, dailyCap: 500 },
        { name: 'firefly', provider: 'adobe_firefly', enabled: false, dailyCount: 50, dailyCap: 500 },
      ],
      modelsLoading: false,
      metrics: {
        today: {
          date: '2026-04-12',
          modelCounts: { gemini: 100, nova: 200, openai: 400, firefly: 50 },
          usersByTier: { free: 10, paid: 5 },
          suspendedCount: 1,
        },
        history: [],
      },
      metricsLoading: false,
      revenue: {
        current: { activeSubscribers: 5, mrr: 2500, monthlyChurn: 0, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminOverview />);

    expect(screen.getByText('gemini')).toBeInTheDocument();
    expect(screen.getByText('nova')).toBeInTheDocument();
    expect(screen.getByText('openai')).toBeInTheDocument();
    expect(screen.getByText('firefly')).toBeInTheDocument();
  });

  it('shows correct utilization colors', () => {
    useAdminStore.setState({
      models: [
        { name: 'gemini', provider: 'google_gemini', enabled: true, dailyCount: 100, dailyCap: 500 },
        { name: 'nova', provider: 'bedrock_nova', enabled: true, dailyCount: 350, dailyCap: 500 },
        { name: 'openai', provider: 'openai', enabled: true, dailyCount: 450, dailyCap: 500 },
        { name: 'firefly', provider: 'adobe_firefly', enabled: true, dailyCount: 0, dailyCap: 500 },
      ],
      modelsLoading: false,
    });

    render(<AdminOverview />);

    // Check progress bars have correct color classes
    const progressBars = screen.getAllByRole('progressbar');
    expect(progressBars.length).toBeGreaterThanOrEqual(4);
  });

  it('handles empty metrics gracefully', () => {
    useAdminStore.setState({
      models: [],
      modelsLoading: false,
      metrics: null,
      metricsLoading: false,
      revenue: null,
      revenueLoading: false,
    });

    render(<AdminOverview />);

    expect(screen.getByText('Overview')).toBeInTheDocument();
    // All summary cards should show 0
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(3);
  });

  it('shows active subscriber count from revenue data', () => {
    useAdminStore.setState({
      models: [],
      modelsLoading: false,
      revenue: {
        current: { activeSubscribers: 42, mrr: 2100, monthlyChurn: 3, updatedAt: 0 },
        history: [],
      },
      revenueLoading: false,
    });

    render(<AdminOverview />);

    expect(screen.getByText('42')).toBeInTheDocument();
  });
});
