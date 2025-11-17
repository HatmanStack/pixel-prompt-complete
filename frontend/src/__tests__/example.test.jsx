/**
 * Verification test to ensure Vitest setup is working correctly
 * Tests the Header component with basic rendering
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AppProvider } from '../context/AppContext';
import Header from '../components/common/Header';

describe('Header Component', () => {
  it('renders the application title', () => {
    render(
      <AppProvider>
        <Header />
      </AppProvider>
    );
    const titleElement = screen.getByText('Pixel Prompt');
    expect(titleElement).toBeInTheDocument();
  });

  it('renders the tagline', () => {
    render(
      <AppProvider>
        <Header />
      </AppProvider>
    );
    const taglineElement = screen.getByText('Text-to-Image Variety Pack');
    expect(taglineElement).toBeInTheDocument();
  });

  it('renders a header element', () => {
    render(
      <AppProvider>
        <Header />
      </AppProvider>
    );
    const headerElement = screen.getByRole('banner');
    expect(headerElement).toBeInTheDocument();
  });

  it('renders navigation buttons', () => {
    render(
      <AppProvider>
        <Header />
      </AppProvider>
    );
    const generateButton = screen.getByRole('button', { name: /generate/i });
    const galleryButton = screen.getByRole('button', { name: /gallery/i });
    expect(generateButton).toBeInTheDocument();
    expect(galleryButton).toBeInTheDocument();
  });
});
