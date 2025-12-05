/**
 * App Component
 * Root application component with Zustand stores, error boundaries,
 * and keyboard shortcut handling
 */

import { useState, useEffect, type FC } from 'react';
import { Header } from '@/components/common/Header';
import { Container } from '@/components/common/Container';
import { Footer } from '@/components/common/Footer';
import { KeyboardShortcutsHelp } from '@/components/common/KeyboardShortcutsHelp';
import { ErrorBoundary } from '@/components/features/errors/ErrorBoundary';
import { ErrorFallback } from '@/components/features/errors/ErrorFallback';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { Suspense, lazy } from 'react';

const GenerationPanel = lazy(() => import('@/components/generation/GenerationPanel'));

export const App: FC = () => {
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only handle shortcuts when not typing in an input/textarea
      const activeEl = document.activeElement as HTMLElement | null;
      const isTyping = ['INPUT', 'TEXTAREA'].includes(activeEl?.tagName ?? '');

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
    <div className="min-h-screen flex flex-col bg-primary">
      {/* Header - outside error boundary, always visible */}
      <Header />

      {/* Main content */}
      <main className="flex-1 flex flex-col py-6">
        <Container>
          <ErrorBoundary
            fallback={(props) => <ErrorFallback {...props} />}
            componentName="GenerationPanel"
          >
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20">
                  <LoadingSpinner size="lg" message="Loading generation panel..." />
                </div>
              }
            >
              <GenerationPanel />
            </Suspense>
          </ErrorBoundary>
        </Container>
      </main>

      {/* Footer - outside error boundary, always visible */}
      <Footer />

      {/* Keyboard Shortcuts Help Dialog */}
      <KeyboardShortcutsHelp
        isOpen={showShortcutsHelp}
        onClose={() => setShowShortcutsHelp(false)}
      />
    </div>
  );
};

export default App;
