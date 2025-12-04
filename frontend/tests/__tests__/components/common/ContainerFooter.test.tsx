/**
 * Tests for Container and Footer components
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Container } from '../../../../src/components/common/Container';
import { Footer } from '../../../../src/components/common/Footer';

describe('Container', () => {
  it('renders children', () => {
    render(<Container>Content</Container>);

    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('applies max-width by default', () => {
    const { container } = render(<Container>Content</Container>);

    expect(container.firstChild).toHaveClass('max-w-7xl');
  });

  it('removes max-width when fullWidth is true', () => {
    const { container } = render(<Container fullWidth>Content</Container>);

    expect(container.firstChild).not.toHaveClass('max-w-7xl');
  });

  it('renders as custom element', () => {
    render(<Container as="section">Content</Container>);

    const section = screen.getByText('Content').closest('section');
    expect(section).toBeInTheDocument();
  });

  it('applies responsive padding', () => {
    const { container } = render(<Container>Content</Container>);

    expect(container.firstChild).toHaveClass('px-4');
    expect(container.firstChild).toHaveClass('sm:px-6');
    expect(container.firstChild).toHaveClass('lg:px-8');
  });

  it('applies custom className', () => {
    const { container } = render(
      <Container className="custom-class">Content</Container>
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });
});

describe('Footer', () => {
  it('renders keyboard shortcuts section', () => {
    render(<Footer />);

    expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument();
  });

  it('renders Ctrl+Enter shortcut', () => {
    render(<Footer />);

    expect(screen.getByText('Ctrl')).toBeInTheDocument();
    expect(screen.getByText('Enter')).toBeInTheDocument();
    expect(screen.getByText('Generate')).toBeInTheDocument();
  });

  it('renders Esc shortcut', () => {
    render(<Footer />);

    expect(screen.getByText('Esc')).toBeInTheDocument();
    expect(screen.getByText('Clear prompt')).toBeInTheDocument();
  });

  it('renders attribution', () => {
    render(<Footer />);

    expect(
      screen.getByText(/Pixel Prompt Complete - Powered by multiple AI models/)
    ).toBeInTheDocument();
  });

  it('uses kbd elements for keys', () => {
    const { container } = render(<Footer />);

    const kbdElements = container.querySelectorAll('kbd');
    expect(kbdElements.length).toBeGreaterThan(0);
  });

  it('applies custom className', () => {
    const { container } = render(<Footer className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('uses footer element', () => {
    render(<Footer />);

    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });
});
