/**
 * Header Component
 * Application header with breathing animation, sound toggle, and navigation
 */

import type { FC } from 'react';
import { useAppStore } from '@/stores/useAppStore';
import { useAuthStore } from '@/stores/useAuthStore';
import { useSound } from '@/hooks/useSound';
import { AUTH_ENABLED, hostedUiLoginUrl, hostedUiLogoutUrl } from '@/api/config';
import { BreathingHeader } from './BreathingHeader';
import { SoundToggle } from './SoundToggle';

interface HeaderProps {
  className?: string;
}

export const Header: FC<HeaderProps> = ({ className = '' }) => {
  const { currentView, setCurrentView } = useAppStore();
  const isAuthed = useAuthStore((s) => s.isAuthenticated());
  const user = useAuthStore((s) => s.user);
  const clearTokens = useAuthStore((s) => s.clearTokens);
  const { playSound } = useSound();

  const handleNavClick = (view: 'generation' | 'gallery') => {
    if (view !== currentView) {
      playSound('switch');
      setCurrentView(view);
    }
  };

  const handleSignOut = () => {
    clearTokens();
    if (typeof window !== 'undefined') {
      window.location.assign(hostedUiLogoutUrl());
    }
  };

  return (
    <header
      className={`
        w-full
        bg-gradient-to-br from-secondary to-primary
        border-b border-primary/50
        px-4 py-4 lg:px-6 lg:py-5
        ${className}
      `}
    >
      <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-center justify-between gap-4">
        {/* Branding with breathing animation */}
        <div className="flex flex-col items-center lg:items-start">
          <BreathingHeader className="text-2xl sm:text-3xl lg:text-4xl" />
          <p className="text-xs sm:text-sm text-text-secondary font-medium tracking-wider uppercase mt-1">
            Text-to-Image Variety Pack
          </p>
        </div>

        {/* Navigation and controls */}
        <div className="flex items-center gap-3">
          <nav className="flex gap-2" role="navigation" aria-label="Main">
            <button
              className={`
                px-4 py-2 rounded-md text-sm font-medium
                transition-all duration-200
                focus:outline-none focus:ring-2 focus:ring-accent
                ${
                  currentView === 'generation'
                    ? 'bg-accent text-white'
                    : 'bg-transparent border border-primary/50 text-text-secondary hover:bg-primary/50 hover:text-text'
                }
              `}
              onClick={() => handleNavClick('generation')}
              aria-current={currentView === 'generation' ? 'page' : undefined}
            >
              Generate
            </button>
            <button
              className={`
                px-4 py-2 rounded-md text-sm font-medium
                transition-all duration-200
                focus:outline-none focus:ring-2 focus:ring-accent
                ${
                  currentView === 'gallery'
                    ? 'bg-accent text-white'
                    : 'bg-transparent border border-primary/50 text-text-secondary hover:bg-primary/50 hover:text-text'
                }
              `}
              onClick={() => handleNavClick('gallery')}
              aria-current={currentView === 'gallery' ? 'page' : undefined}
            >
              Gallery
            </button>
          </nav>

          {/* Sound toggle */}
          <SoundToggle />

          {/* Auth controls */}
          {AUTH_ENABLED && (
            <div className="flex items-center gap-2" data-testid="auth-controls">
              {isAuthed ? (
                <>
                  <span className="text-xs text-text-secondary hidden sm:inline">
                    {user?.email}
                  </span>
                  <button
                    type="button"
                    onClick={handleSignOut}
                    className="px-3 py-1.5 rounded text-sm border border-primary/50 text-text-secondary hover:text-text"
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <a
                  href={hostedUiLoginUrl()}
                  className="px-3 py-1.5 rounded text-sm bg-accent text-white"
                >
                  Sign in
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
