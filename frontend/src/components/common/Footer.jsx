/**
 * Footer Component
 * Application footer with keyboard shortcuts and help
 */

import styles from './Footer.module.css';

function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.content}>
        <div className={styles.shortcuts}>
          <h4>Keyboard Shortcuts:</h4>
          <div className={styles.shortcutList}>
            <span className={styles.shortcut}>
              <kbd>Ctrl</kbd> + <kbd>Enter</kbd> - Generate
            </span>
            <span className={styles.shortcut}>
              <kbd>Esc</kbd> - Clear prompt
            </span>
          </div>
        </div>

        <div className={styles.info}>
          <p>Pixel Prompt Complete - Powered by multiple AI models</p>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
