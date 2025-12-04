/**
 * DesktopLayout Component
 * Two-column layout for desktop: gallery (left) and generation (right)
 */

import type { FC, ReactNode } from 'react';

interface DesktopLayoutProps {
  gallery: ReactNode;
  generation: ReactNode;
  className?: string;
}

export const DesktopLayout: FC<DesktopLayoutProps> = ({
  gallery,
  generation,
  className = '',
}) => {
  return (
    <div
      className={`
        grid grid-cols-2 gap-4 h-full w-full
        ${className}
      `}
    >
      {/* Gallery panel - left side */}
      <section
        className="flex flex-col overflow-hidden rounded-lg bg-secondary"
        aria-label="Gallery"
      >
        {gallery}
      </section>

      {/* Generation panel - right side */}
      <section
        className="flex flex-col overflow-hidden rounded-lg bg-secondary"
        aria-label="Generation"
      >
        {generation}
      </section>
    </div>
  );
};

export default DesktopLayout;
