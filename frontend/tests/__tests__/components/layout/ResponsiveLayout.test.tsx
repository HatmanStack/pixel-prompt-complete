/**
 * Tests for ResponsiveLayout component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ResponsiveLayout } from '../../../../src/components/layout/ResponsiveLayout';
import * as useBreakpointModule from '../../../../src/hooks/useBreakpoint';

// Mock the useBreakpoint hook
vi.mock('../../../../src/hooks/useBreakpoint', () => ({
  useBreakpoint: vi.fn(),
}));

// Mock the UI store
vi.mock('../../../../src/stores/useUIStore', () => ({
  useUIStore: () => ({
    isGalleryDrawerOpen: false,
    toggleGalleryDrawer: vi.fn(),
  }),
}));

describe('ResponsiveLayout', () => {
  const mockGallery = <div data-testid="gallery">Gallery Content</div>;
  const mockGeneration = <div data-testid="generation">Generation Content</div>;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders DesktopLayout when isDesktop is true', () => {
    vi.mocked(useBreakpointModule.useBreakpoint).mockReturnValue({
      breakpoint: 'lg',
      isDesktop: true,
      isMobile: false,
      isSmall: false,
      isMedium: false,
      isLarge: true,
      isExtraLarge: false,
    });

    render(
      <ResponsiveLayout gallery={mockGallery} generation={mockGeneration} />
    );

    expect(screen.getByTestId('gallery')).toBeInTheDocument();
    expect(screen.getByTestId('generation')).toBeInTheDocument();
    // Desktop layout should have grid
    expect(screen.getByRole('region', { name: 'Gallery' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Generation' })).toBeInTheDocument();
  });

  it('renders MobileLayout when isDesktop is false', () => {
    vi.mocked(useBreakpointModule.useBreakpoint).mockReturnValue({
      breakpoint: 'sm',
      isDesktop: false,
      isMobile: true,
      isSmall: true,
      isMedium: false,
      isLarge: false,
      isExtraLarge: false,
    });

    render(
      <ResponsiveLayout gallery={mockGallery} generation={mockGeneration} />
    );

    expect(screen.getByTestId('generation')).toBeInTheDocument();
    // Mobile should have a toggle button
    expect(
      screen.getByRole('button', { name: /gallery/i })
    ).toBeInTheDocument();
  });

  it('passes className to layout components', () => {
    vi.mocked(useBreakpointModule.useBreakpoint).mockReturnValue({
      breakpoint: 'lg',
      isDesktop: true,
      isMobile: false,
      isSmall: false,
      isMedium: false,
      isLarge: true,
      isExtraLarge: false,
    });

    const { container } = render(
      <ResponsiveLayout
        gallery={mockGallery}
        generation={mockGeneration}
        className="custom-class"
      />
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
