/**
 * ResponsiveLayout Component
 * Renders DesktopLayout or MobileLayout based on screen size
 */

import type { FC, ReactNode } from 'react';
import { useBreakpoint } from '@/hooks/useBreakpoint';
import { DesktopLayout } from './DesktopLayout';
import { MobileLayout } from './MobileLayout';

interface ResponsiveLayoutProps {
  gallery: ReactNode;
  generation: ReactNode;
  className?: string;
}

export const ResponsiveLayout: FC<ResponsiveLayoutProps> = ({
  gallery,
  generation,
  className = '',
}) => {
  const { isDesktop } = useBreakpoint();

  if (isDesktop) {
    return <DesktopLayout gallery={gallery} generation={generation} className={className} />;
  }

  return <MobileLayout gallery={gallery} generation={generation} className={className} />;
};

export default ResponsiveLayout;
