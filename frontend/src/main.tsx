/**
 * Application Entry Point
 * Sets up React with providers and renders the App
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ToastContainer } from '@/components/common/ToastContainer';
import App from './App';
import './index.css';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Root element not found');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
    <ToastContainer />
  </StrictMode>,
);
