/**
 * MobileLayout Component
 * Single-column layout for mobile with gallery toggle
 */

import type { FC, ReactNode } from 'react';
import { useUIStore } from '@/stores/useUIStore';

interface MobileLayoutProps {
  gallery: ReactNode;
  generation: ReactNode;
  className?: string;
}

export const MobileLayout: FC<MobileLayoutProps> = ({
  gallery,
  generation,
  className = '',
}) => {
  const { isGalleryDrawerOpen, toggleGalleryDrawer } = useUIStore();

  return (
    <div className={`relative flex flex-col h-full w-full ${className}`}>
      {/* Main content - generation panel */}
      <main className="flex-1 overflow-hidden">
        <section
          className="h-full flex flex-col rounded-lg bg-secondary"
          aria-label="Generation"
        >
          {generation}
        </section>
      </main>

      {/* Gallery toggle button */}
      <button
        onClick={toggleGalleryDrawer}
        className="
          fixed bottom-4 left-4 z-40
          flex items-center justify-center
          w-12 h-12
          bg-accent text-white rounded-full shadow-lg
          hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent
          transition-colors
        "
        aria-label={isGalleryDrawerOpen ? 'Close gallery' : 'Open gallery'}
        aria-expanded={isGalleryDrawerOpen}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="w-6 h-6"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"
          />
        </svg>
      </button>

      {/* Gallery drawer overlay */}
      {isGalleryDrawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 transition-opacity"
          onClick={toggleGalleryDrawer}
          aria-hidden="true"
        />
      )}

      {/* Gallery drawer */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50
          w-4/5 max-w-sm
          bg-secondary shadow-xl
          transform transition-transform duration-300 ease-in-out
          ${isGalleryDrawerOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        aria-label="Gallery drawer"
        aria-hidden={!isGalleryDrawerOpen}
      >
        <div className="h-full flex flex-col">
          {/* Drawer header */}
          <div className="flex items-center justify-between p-4 border-b border-primary">
            <h2 className="text-lg font-display text-accent">Gallery</h2>
            <button
              onClick={toggleGalleryDrawer}
              className="
                p-2 rounded-md
                text-text-secondary hover:text-text
                hover:bg-primary transition-colors
              "
              aria-label="Close gallery"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Gallery content */}
          <div className="flex-1 overflow-auto">
            {gallery}
          </div>
        </div>
      </aside>
    </div>
  );
};

export default MobileLayout;
