/**
 * AdminRevenue - Revenue reporting section.
 * Shows active subscriber count, churn metrics, and historical trends.
 */

import { useEffect, useState, type FC } from 'react';
import { useAdminStore } from '@/stores/useAdminStore';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

export const AdminRevenue: FC = () => {
  const { revenue, revenueLoading, fetchRevenue, fetchMetrics } = useAdminStore();
  const [dateRange, setDateRange] = useState(7);

  useEffect(() => {
    fetchRevenue();
    fetchMetrics(dateRange);
  }, [fetchRevenue, fetchMetrics, dateRange]);

  const activeSubscribers = revenue?.current?.activeSubscribers ?? 0;
  const monthlyChurn = revenue?.current?.monthlyChurn ?? 0;
  const churnRate =
    activeSubscribers > 0 ? ((monthlyChurn / activeSubscribers) * 100).toFixed(1) : '0.0';

  // Build chart data from history snapshots
  const chartData =
    revenue?.history?.map((snapshot) => ({
      date: snapshot.date,
      subscribers: snapshot.revenue?.activeSubscribers ?? 0,
    })) ?? [];

  const handleDateRange = (days: number) => {
    setDateRange(days);
    fetchMetrics(days);
  };

  if (revenueLoading && !revenue) {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">Revenue</h2>
        <div className="text-gray-400 animate-pulse">Loading revenue data...</div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Revenue</h2>

      {/* Key metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Active Subscribers</div>
          <div className="text-2xl font-bold">{activeSubscribers}</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Monthly Churn</div>
          <div className="text-2xl font-bold">{monthlyChurn}</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Churn Rate</div>
          <div className="text-2xl font-bold">{churnRate}%</div>
        </div>
      </div>

      {/* Date range selector */}
      <div className="flex gap-2 mb-4">
        {[7, 14, 30].map((days) => (
          <button
            key={days}
            className={`px-3 py-1 rounded text-sm ${
              dateRange === days
                ? 'bg-accent text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
            onClick={() => handleDateRange(days)}
          >
            {days} days
          </button>
        ))}
      </div>

      {/* Historical subscriber trend chart */}
      {chartData.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h3 className="text-lg font-medium mb-3">Subscriber Trend</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#D1D5DB' }}
              />
              <Area
                type="monotone"
                dataKey="subscribers"
                stroke="#6366F1"
                fill="#6366F1"
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};
