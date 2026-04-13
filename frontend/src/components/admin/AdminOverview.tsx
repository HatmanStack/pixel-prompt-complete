/**
 * AdminOverview - Dashboard overview section.
 * Shows model status cards with utilization progress bars,
 * today's generation totals, and active subscriber count.
 */

import { useEffect, type FC } from 'react';
import { useAdminStore } from '@/stores/useAdminStore';

function utilizationColor(percent: number): string {
  if (percent >= 80) return 'bg-red-500';
  if (percent >= 50) return 'bg-yellow-500';
  return 'bg-green-500';
}

const ModelCard: FC<{
  name: string;
  enabled: boolean;
  dailyCount: number;
  dailyCap: number;
}> = ({ name, enabled, dailyCount, dailyCap }) => {
  const percent = dailyCap > 0 ? Math.min((dailyCount / dailyCap) * 100, 100) : 0;

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium">{name}</span>
        <span
          className={`text-xs px-2 py-0.5 rounded ${enabled ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}
        >
          {enabled ? 'Enabled' : 'Disabled'}
        </span>
      </div>
      <div className="text-sm text-gray-400 mb-1">
        {dailyCount} / {dailyCap}
      </div>
      <div
        className="w-full h-2 bg-gray-700 rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${name} utilization`}
      >
        <div
          className={`h-full rounded-full transition-all ${utilizationColor(percent)}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
};

export const AdminOverview: FC = () => {
  const {
    models,
    modelsLoading,
    metrics,
    metricsLoading,
    revenue,
    revenueLoading,
    fetchModels,
    fetchMetrics,
    fetchRevenue,
  } = useAdminStore();

  useEffect(() => {
    fetchModels();
    fetchMetrics(7);
    fetchRevenue();
  }, [fetchModels, fetchMetrics, fetchRevenue]);

  const totalGenerations = models.reduce((sum, m) => sum + m.dailyCount, 0);
  const activeSubscribers = revenue?.current?.activeSubscribers ?? 0;
  const suspendedCount = metrics?.today?.suspendedCount ?? 0;

  const isLoading = modelsLoading || metricsLoading || revenueLoading;

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Overview</h2>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Total Generations Today</div>
          <div className="text-2xl font-bold">{totalGenerations}</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Active Subscribers</div>
          <div className="text-2xl font-bold">{activeSubscribers}</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Suspended Accounts</div>
          <div className="text-2xl font-bold">{suspendedCount}</div>
        </div>
      </div>

      {/* Model status cards */}
      <h3 className="text-lg font-medium mb-3">Model Status</h3>
      {isLoading && models.length === 0 ? (
        <div className="text-gray-400 animate-pulse">Loading model data...</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {models.map((model) => (
            <ModelCard
              key={model.name}
              name={model.name}
              enabled={model.enabled}
              dailyCount={model.dailyCount}
              dailyCap={model.dailyCap}
            />
          ))}
        </div>
      )}

      {/* 7-day history */}
      {metrics?.history && metrics.history.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-medium mb-3">7-Day Generation History</h3>
          <div className="flex items-end gap-1 h-24">
            {metrics.history.map((snapshot, i) => {
              const total = Object.values(snapshot.modelCounts || {}).reduce((s, c) => s + c, 0);
              const maxTotal = Math.max(
                ...metrics.history.map((h) =>
                  Object.values(h.modelCounts || {}).reduce((s, c) => s + c, 0),
                ),
                1,
              );
              const height = (total / maxTotal) * 100;
              return (
                <div
                  key={i}
                  className="flex-1 bg-accent/70 rounded-t"
                  style={{ height: `${height}%` }}
                  title={`${snapshot.date}: ${total} generations`}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
