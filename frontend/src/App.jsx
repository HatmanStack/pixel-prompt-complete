/**
 * App Component
 * Root application component with error boundaries and lazy-loaded routes
 * Handles global keyboard shortcuts
 */

import { useState, useEffect } from 'react';
import Header from './components/common/Header';
import Container from './components/common/Container';
import Footer from './components/common/Footer';
import GenerationPanel from './components/generation/GenerationPanel';
import KeyboardShortcutsHelp from './components/common/KeyboardShortcutsHelp';
import ErrorBoundary from './components/features/errors/ErrorBoundary';
import ErrorFallback from './components/features/errors/ErrorFallback';
import styles from './App.module.css';

function App() {
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Only handle shortcuts when not typing in an input/textarea
      const isTyping = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);

      if ((e.ctrlKey || e.metaKey) && e.key === 'k' && !isTyping) {
        e.preventDefault();
        setShowShortcutsHelp(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  return (
    <div className={styles.app}>
      {/* Keep Header and Footer outside error boundary - always visible */}
      <Header />
      <main className={styles.main}>
        <Container>
          <ErrorBoundary
            fallback={ErrorFallback}
            componentName="GenerationPanel"
          >
            <GenerationPanel />
          </ErrorBoundary>
        </Container>
      </main>
      <Footer />

      {/* Keyboard Shortcuts Help Dialog */}
      <KeyboardShortcutsHelp
        isOpen={showShortcutsHelp}
        onClose={() => setShowShortcutsHelp(false)}
      />
    </div>
  );
}

export default App;
