/**
 * Application Entry Point
 * Sets up React with providers and renders the App
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ToastContainer } from '@/components/common/ToastContainer';
import { configErrors } from '@/api/config';
import { renderConfigDiagnostic } from '@/components/errors/configDiagnostic';
import App from './App';
import './index.css';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Root element not found');
}

if (configErrors.length > 0) {
  // Rendered INSTEAD of the app, not alongside it. Mounting an app that is
  // missing VITE_API_ENDPOINT would trade a blank page for a confusing one:
  // every request would fail with an unexplained network error and nothing
  // would say why. A misconfigured build should stay loud.
  renderConfigDiagnostic(configErrors, rootElement);
} else {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
      <ToastContainer />
    </StrictMode>,
  );
}
