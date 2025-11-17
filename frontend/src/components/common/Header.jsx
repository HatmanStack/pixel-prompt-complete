/**
 * Header Component
 * Application header with branding and navigation
 */

import { useApp } from '../../context/AppContext';
import styles from './Header.module.css';

function Header() {
  const { currentView, setCurrentView } = useApp();

  return (
    <header className={styles.header}>
      <div className={styles.content}>
        <div className={styles.branding}>
          <h1 className={styles.title}>Pixel Prompt</h1>
          <p className={styles.tagline}>Text-to-Image Variety Pack</p>
        </div>
        <nav className={styles.nav}>
          <button
            className={`${styles.navButton} ${currentView === 'generation' ? styles.active : ''}`}
            onClick={() => setCurrentView('generation')}
            aria-current={currentView === 'generation' ? 'page' : undefined}
          >
            Generate
          </button>
          <button
            className={`${styles.navButton} ${currentView === 'gallery' ? styles.active : ''}`}
            onClick={() => setCurrentView('gallery')}
            aria-current={currentView === 'gallery' ? 'page' : undefined}
          >
            Gallery
          </button>
        </nav>
      </div>
    </header>
  );
}

export default Header;
