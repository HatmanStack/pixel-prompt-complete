/**
 * Header Component
 * Application header with breathing animation, sound toggle, and navigation
 */

import type { FC } from 'react';
import { useAppStore } from '@/stores/useAppStore';
import { useSound } from '@/hooks/useSound';
import { BreathingHeader } from './BreathingHeader';
import { SoundToggle } from './SoundToggle';

interface HeaderProps {
  className?: string;
}

export const Header: FC<HeaderProps> = ({ className = '' }) => {
  const { currentView, setCurrentView } = useAppStore();
  const { playSound } = useSound();

  const handleNavClick = (view: 'generation' | 'gallery') => {
    if (view !== currentView) {
      playSound('switch');
      setCurrentView(view);
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
        </div>
      </div>
    </header>
  );
};

export default Header;
