/**
 * AdminModels tests.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

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

// Mock recharts to avoid rendering issues in test environment
vi.mock('recharts', () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  CartesianGrid: () => <div />,
}));

import { useAdminStore } from '../../../../src/stores/useAdminStore';
import { AdminModels } from '../../../../src/components/admin/AdminModels';

const sampleModels = [
  { name: 'gemini', provider: 'google_gemini', enabled: true, dailyCount: 100, dailyCap: 500 },
  { name: 'nova', provider: 'bedrock_nova', enabled: true, dailyCount: 350, dailyCap: 500 },
  { name: 'openai', provider: 'openai', enabled: true, dailyCount: 450, dailyCap: 500 },
  { name: 'firefly', provider: 'adobe_firefly', enabled: false, dailyCount: 50, dailyCap: 500 },
];

describe('AdminModels', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    useAdminStore.setState({
      models: sampleModels,
      modelsLoading: false,
      metrics: null,
      metricsLoading: false,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders all 4 model cards', () => {
    render(<AdminModels />);

    expect(screen.getByText('gemini')).toBeInTheDocument();
    expect(screen.getByText('nova')).toBeInTheDocument();
    // openai appears as both model name and provider, so use getAllByText
    expect(screen.getAllByText('openai').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('firefly')).toBeInTheDocument();
  });

  it('shows progress bars with count vs cap', () => {
    render(<AdminModels />);

    const progressBars = screen.getAllByRole('progressbar');
    expect(progressBars).toHaveLength(4);

    // gemini: 100/500 = 20%
    expect(progressBars[0]).toHaveAttribute('aria-valuenow', '20');
    // nova: 350/500 = 70%
    expect(progressBars[1]).toHaveAttribute('aria-valuenow', '70');
    // openai: 450/500 = 90%
    expect(progressBars[2]).toHaveAttribute('aria-valuenow', '90');
    // firefly: 50/500 = 10%
    expect(progressBars[3]).toHaveAttribute('aria-valuenow', '10');
  });

  it('shows enabled/disabled status badges', () => {
    render(<AdminModels />);

    const enabledBadges = screen.getAllByText('Enabled');
    const disabledBadges = screen.getAllByText('Disabled');
    expect(enabledBadges).toHaveLength(3);
    expect(disabledBadges).toHaveLength(1);
  });

  it('shows disable button for enabled models and enable button for disabled models', () => {
    render(<AdminModels />);

    const disableButtons = screen.getAllByRole('button', { name: /disable/i });
    const enableButtons = screen.getAllByRole('button', { name: /enable/i });
    expect(disableButtons).toHaveLength(3);
    expect(enableButtons).toHaveLength(1);
  });

  it('shows confirmation dialog when disable button is clicked', () => {
    render(<AdminModels />);

    const disableButtons = screen.getAllByRole('button', { name: /disable/i });
    fireEvent.click(disableButtons[0]);

    expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
  });

  it('calls disableModel on confirmation', async () => {
    const disableModelFn = vi.fn().mockResolvedValue(undefined);
    useAdminStore.setState({ disableModel: disableModelFn });

    render(<AdminModels />);

    const disableButtons = screen.getAllByRole('button', { name: /disable/i });
    fireEvent.click(disableButtons[0]);

    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    expect(disableModelFn).toHaveBeenCalledWith('gemini');
  });

  it('calls enableModel directly without confirmation', async () => {
    const enableModelFn = vi.fn().mockResolvedValue(undefined);
    useAdminStore.setState({ enableModel: enableModelFn });

    render(<AdminModels />);

    const enableButton = screen.getByRole('button', { name: /enable/i });
    await act(async () => {
      fireEvent.click(enableButton);
    });

    expect(enableModelFn).toHaveBeenCalledWith('firefly');
  });

  it('shows loading state when models are loading', () => {
    useAdminStore.setState({ models: [], modelsLoading: true });

    render(<AdminModels />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders historical chart when metrics history is available', () => {
    useAdminStore.setState({
      metrics: {
        today: null,
        history: [
          {
            date: '2026-04-10',
            modelCounts: { gemini: 100, nova: 200 },
            usersByTier: {},
            suspendedCount: 0,
          },
          {
            date: '2026-04-11',
            modelCounts: { gemini: 150, nova: 250 },
            usersByTier: {},
            suspendedCount: 0,
          },
        ],
      },
      metricsLoading: false,
    });

    render(<AdminModels />);

    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });
});
