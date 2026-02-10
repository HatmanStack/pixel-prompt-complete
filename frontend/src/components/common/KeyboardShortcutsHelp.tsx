/**
 * KeyboardShortcutsHelp Component
 * Modal dialog displaying all available keyboard shortcuts
 * Platform-aware (shows Ctrl on Windows/Linux, Cmd on Mac)
 */

import { useMemo, type FC } from 'react';
import { Modal } from './Modal';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

interface Shortcut {
  action: string;
  keys: string[];
  description: string;
}

interface ShortcutSection {
  category: string;
  items: Shortcut[];
}

export const KeyboardShortcutsHelp: FC<KeyboardShortcutsHelpProps> = ({ isOpen, onClose }) => {
  const isMac = useMemo(() => {
    if (typeof navigator !== 'undefined') {
      return navigator.platform?.toUpperCase().includes('MAC') ?? false;
    }
    return false;
  }, []);

  const modifier = isMac ? '⌘' : 'Ctrl';

  const shortcuts: ShortcutSection[] = [
    {
      category: 'Generation',
      items: [
        {
          action: 'Generate Images',
          keys: [modifier, 'Enter'],
          description: 'Start image generation with current prompt',
        },
        {
          action: 'Random Prompt',
          keys: [modifier, 'R'],
          description: 'Fill prompt with random inspiration',
        },
        {
          action: 'Enhance Prompt',
          keys: [modifier, 'E'],
          description: 'AI-enhance current prompt',
        },
      ],
    },
    {
      category: 'Downloads',
      items: [
        {
          action: 'Download Image',
          keys: [modifier, 'D'],
          description: 'Download currently focused image',
        },
        {
          action: 'Download All',
          keys: [modifier, '⇧', 'D'],
          description: 'Download all completed images',
        },
      ],
    },
    {
      category: 'Navigation',
      items: [
        {
          action: 'Previous Image',
          keys: ['←'],
          description: 'Navigate to previous image in modal',
        },
        {
          action: 'Next Image',
          keys: ['→'],
          description: 'Navigate to next image in modal',
        },
        {
          action: 'Close Modal',
          keys: ['Esc'],
          description: 'Close modal or dialog',
        },
      ],
    },
    {
      category: 'Utility',
      items: [
        {
          action: 'Keyboard Shortcuts',
          keys: [modifier, 'K'],
          description: 'Show this help dialog',
        },
      ],
    },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Keyboard Shortcuts"
      ariaLabel="Keyboard shortcuts help"
      size="md"
    >
      <div className="space-y-6">
        <p className="text-sm text-text-secondary">
          {isMac ? 'macOS shortcuts use ⌘ (Command)' : 'Windows/Linux shortcuts use Ctrl'}
        </p>

        {shortcuts.map((section) => (
          <div key={section.category}>
            <h3 className="text-sm font-medium text-accent uppercase tracking-wider mb-3">
              {section.category}
            </h3>
            <div className="space-y-2">
              {section.items.map((shortcut) => (
                <div key={shortcut.action} className="flex items-center gap-4 py-2">
                  <div className="w-32 font-medium text-text">{shortcut.action}</div>
                  <div className="flex items-center gap-1">
                    {shortcut.keys.map((key, index) => (
                      <span key={index} className="flex items-center">
                        <kbd className="px-2 py-1 bg-primary rounded text-xs font-mono text-text-secondary">
                          {key}
                        </kbd>
                        {index < shortcut.keys.length - 1 && (
                          <span className="mx-1 text-text-secondary">+</span>
                        )}
                      </span>
                    ))}
                  </div>
                  <div className="flex-1 text-sm text-text-secondary">{shortcut.description}</div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <div className="pt-4 border-t border-primary/30">
          <p className="text-sm text-text-secondary">
            Tip: Press <kbd className="px-2 py-0.5 bg-primary rounded text-xs font-mono">Esc</kbd>{' '}
            to close this dialog
          </p>
        </div>
      </div>
    </Modal>
  );
};

export default KeyboardShortcutsHelp;
