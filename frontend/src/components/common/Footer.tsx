/**
 * Footer Component
 * Application footer with keyboard shortcuts and attribution
 */

import type { FC } from 'react';

interface FooterProps {
  className?: string;
}

export const Footer: FC<FooterProps> = ({ className = '' }) => {
  return (
    <footer
      className={`
        w-full
        bg-secondary border-t border-primary/30
        px-4 py-4
        ${className}
      `}
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Keyboard shortcuts */}
        <div className="text-center sm:text-left">
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
            Keyboard Shortcuts
          </h4>
          <div className="flex flex-wrap gap-3 justify-center sm:justify-start text-sm text-text-secondary">
            <span className="flex items-center gap-1">
              <kbd className="px-2 py-0.5 bg-primary rounded text-xs font-mono">Ctrl</kbd>+
              <kbd className="px-2 py-0.5 bg-primary rounded text-xs font-mono">Enter</kbd>
              <span className="ml-1">Generate</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-2 py-0.5 bg-primary rounded text-xs font-mono">Esc</kbd>
              <span className="ml-1">Clear prompt</span>
            </span>
          </div>
        </div>

        {/* Attribution */}
        <p className="text-xs text-text-secondary text-center sm:text-right">
          Pixel Prompt Complete - Powered by multiple AI models
        </p>
      </div>
    </footer>
  );
};

export default Footer;
