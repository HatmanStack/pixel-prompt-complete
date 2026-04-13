/**
 * AdminModels - Model management section.
 * Shows per-model cards with daily count progress bars,
 * disable/enable toggles with confirmation, and historical charts.
 * Auto-refreshes every 30 seconds.
 */

import { useEffect, useState, useCallback, type FC } from 'react';
import { useAdminStore } from '@/stores/useAdminStore';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

function utilizationColor(percent: number): string {
  if (percent >= 80) return 'bg-red-500';
  if (percent >= 50) return 'bg-yellow-500';
  return 'bg-green-500';
}

interface ModelCardProps {
  name: string;
  provider: string;
  enabled: boolean;
  dailyCount: number;
  dailyCap: number;
  onDisable: (name: string) => void;
  onEnable: (name: string) => void;
}

const ModelCard: FC<ModelCardProps> = ({
  name,
  provider,
  enabled,
  dailyCount,
  dailyCap,
  onDisable,
  onEnable,
}) => {
  const [showConfirm, setShowConfirm] = useState(false);
  const percent = dailyCap > 0 ? Math.min((dailyCount / dailyCap) * 100, 100) : 0;

  const handleDisableClick = () => {
    setShowConfirm(true);
  };

  const handleConfirm = () => {
    onDisable(name);
    setShowConfirm(false);
  };

  const handleCancel = () => {
    setShowConfirm(false);
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="font-medium">{name}</span>
          <span className="text-xs text-gray-400 ml-2">{provider}</span>
        </div>
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
        className="w-full h-3 bg-gray-700 rounded-full overflow-hidden mb-3"
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

      {showConfirm ? (
        <div className="flex items-center gap-2">
          <span className="text-sm text-yellow-300">Are you sure?</span>
          <button
            className="text-xs px-2 py-1 bg-red-700 text-white rounded hover:bg-red-600"
            onClick={handleConfirm}
          >
            Confirm
          </button>
          <button
            className="text-xs px-2 py-1 bg-gray-600 text-white rounded hover:bg-gray-500"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          className={`text-xs px-3 py-1 rounded ${
            enabled
              ? 'bg-red-900 text-red-300 hover:bg-red-800'
              : 'bg-green-900 text-green-300 hover:bg-green-800'
          }`}
          onClick={enabled ? handleDisableClick : () => onEnable(name)}
        >
          {enabled ? 'Disable' : 'Enable'}
        </button>
      )}
    </div>
  );
};

export const AdminModels: FC = () => {
  const { models, modelsLoading, metrics, fetchModels, fetchMetrics, disableModel, enableModel } =
    useAdminStore();

  const handleDisable = useCallback(
    async (name: string) => {
      await disableModel(name);
    },
    [disableModel],
  );

  const handleEnable = useCallback(
    async (name: string) => {
      await enableModel(name);
    },
    [enableModel],
  );

  useEffect(() => {
    fetchModels();
    fetchMetrics(7);
  }, [fetchModels, fetchMetrics]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchModels();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchModels]);

  // Build chart data from metrics history
  const chartData =
    metrics?.history?.map((snapshot) => {
      const total = Object.values(snapshot.modelCounts || {}).reduce((s, c) => s + c, 0);
      return { date: snapshot.date, total, ...snapshot.modelCounts };
    }) ?? [];

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Models</h2>

      {modelsLoading && models.length === 0 ? (
        <div className="text-gray-400 animate-pulse">Loading model data...</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {models.map((model) => (
            <ModelCard
              key={model.name}
              name={model.name}
              provider={model.provider}
              enabled={model.enabled}
              dailyCount={model.dailyCount}
              dailyCap={model.dailyCap}
              onDisable={handleDisable}
              onEnable={handleEnable}
            />
          ))}
        </div>
      )}

      {chartData.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-medium mb-3">7-Day Daily Counts</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#D1D5DB' }}
              />
              <Bar dataKey="total" fill="#6366F1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};
