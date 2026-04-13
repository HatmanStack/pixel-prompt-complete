/**
 * AdminLayout - Admin dashboard shell with sidebar navigation.
 * Renders 5 sections: Overview, Users, Models, Notifications, Revenue.
 * Responsive: sidebar on desktop, top tabs on mobile.
 */

import { useState, type FC } from 'react';
import { AdminOverview } from './AdminOverview';
import { AdminUsers } from './AdminUsers';
import { AdminModels } from './AdminModels';
import { AdminNotifications } from './AdminNotifications';
import { AdminRevenue } from './AdminRevenue';

type Section = 'overview' | 'users' | 'models' | 'notifications' | 'revenue';

const NAV_ITEMS: { key: Section; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'users', label: 'Users' },
  { key: 'models', label: 'Models' },
  { key: 'notifications', label: 'Notifications' },
  { key: 'revenue', label: 'Revenue' },
];

export const AdminLayout: FC = () => {
  const [activeSection, setActiveSection] = useState<Section>('overview');

  const renderSection = () => {
    switch (activeSection) {
      case 'overview':
        return <AdminOverview />;
      case 'users':
        return <AdminUsers />;
      case 'models':
        return <AdminModels />;
      case 'notifications':
        return <AdminNotifications />;
      case 'revenue':
        return <AdminRevenue />;
    }
  };

  return (
    <div className="min-h-screen bg-primary text-white">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold mb-6">Admin Dashboard</h1>

        <div className="flex flex-col md:flex-row gap-6">
          {/* Sidebar (desktop) / Top tabs (mobile) */}
          <nav className="md:w-48 flex-shrink-0">
            <ul className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible">
              {NAV_ITEMS.map((item) => (
                <li key={item.key}>
                  <button
                    onClick={() => setActiveSection(item.key)}
                    className={`
                      w-full text-left px-4 py-2 rounded text-sm font-medium
                      transition-colors whitespace-nowrap
                      ${
                        activeSection === item.key
                          ? 'bg-accent text-white'
                          : 'text-gray-400 hover:text-white hover:bg-gray-800'
                      }
                    `}
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          {/* Main content */}
          <div className="flex-1 min-w-0">{renderSection()}</div>
        </div>
      </div>
    </div>
  );
};
