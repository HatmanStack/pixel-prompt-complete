/**
 * KeyboardShortcutsHelp Component
 * Modal dialog displaying all available keyboard shortcuts
 * Platform-aware (shows Ctrl on Windows/Linux, Cmd on Mac)
 */

import { useEffect, useState } from 'react';
import Modal from './Modal';
import styles from './KeyboardShortcutsHelp.module.css';

function KeyboardShortcutsHelp({ isOpen, onClose }) {
  const [isMac, setIsMac] = useState(false);

  useEffect(() => {
    // Detect if user is on Mac (defensive for non-browser/SSR)
    if (typeof navigator !== 'undefined' && navigator.platform) {
      setIsMac(navigator.platform.toUpperCase().includes('MAC'));
    }
  }, []);

  const modifier = isMac ? '⌘' : 'Ctrl';

  const shortcuts = [
    {
      category: 'Generation',
      items: [
        { action: 'Generate Images', keys: [`${modifier}`, 'Enter'], description: 'Start image generation with current prompt' },
        { action: 'Random Prompt', keys: [`${modifier}`, 'R'], description: 'Fill prompt with random inspiration' },
        { action: 'Enhance Prompt', keys: [`${modifier}`, 'E'], description: 'AI-enhance current prompt' },
      ]
    },
    {
      category: 'Downloads',
      items: [
        { action: 'Download Image', keys: [`${modifier}`, 'D'], description: 'Download currently focused image' },
        { action: 'Download All', keys: [`${modifier}`, '⇧', 'D'], description: 'Download all completed images' },
      ]
    },
    {
      category: 'Navigation',
      items: [
        { action: 'Previous Image', keys: ['←'], description: 'Navigate to previous image in modal' },
        { action: 'Next Image', keys: ['→'], description: 'Navigate to next image in modal' },
        { action: 'Close Modal', keys: ['Esc'], description: 'Close modal or dialog' },
      ]
    },
    {
      category: 'Utility',
      items: [
        { action: 'Keyboard Shortcuts', keys: [`${modifier}`, 'K'], description: 'Show this help dialog' },
      ]
    },
  ];

  return (
    <Modal isOpen={isOpen} onClose={onClose} ariaLabel="Keyboard shortcuts help">
      <div className={styles.container}>
        <h2 className={styles.title}>Keyboard Shortcuts</h2>
        <p className={styles.subtitle}>
          {isMac ? 'macOS shortcuts use ⌘ (Command)' : 'Windows/Linux shortcuts use Ctrl'}
        </p>

        {shortcuts.map((section) => (
          <div key={section.category} className={styles.section}>
            <h3 className={styles.categoryTitle}>{section.category}</h3>
            <div className={styles.shortcuts}>
              {section.items.map((shortcut) => (
                <div key={shortcut.action} className={styles.shortcut}>
                  <div className={styles.action}>{shortcut.action}</div>
                  <div className={styles.keys}>
                    {shortcut.keys.map((key, index) => (
                      <span key={index}>
                        <kbd className={styles.key}>{key}</kbd>
                        {index < shortcut.keys.length - 1 && <span className={styles.plus}>+</span>}
                      </span>
                    ))}
                  </div>
                  <div className={styles.description}>{shortcut.description}</div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <div className={styles.footer}>
          <p className={styles.note}>
            Tip: Press <kbd className={styles.key}>Esc</kbd> to close this dialog
          </p>
        </div>
      </div>
    </Modal>
  );
}

export default KeyboardShortcutsHelp;
