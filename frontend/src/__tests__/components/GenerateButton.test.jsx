/**
 * Tests for GenerateButton Component
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GenerateButton from '../../components/generation/GenerateButton';

describe('GenerateButton', () => {
  const mockOnClick = vi.fn();

  beforeEach(() => {
    mockOnClick.mockClear();
  });

  it('renders with default label', () => {
    render(<GenerateButton onClick={mockOnClick} />);
    expect(screen.getByText('Generate Images')).toBeInTheDocument();
  });

  it('renders with custom label', () => {
    render(<GenerateButton onClick={mockOnClick} label="Custom Label" />);
    expect(screen.getByText('Custom Label')).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const user = userEvent.setup();
    render(<GenerateButton onClick={mockOnClick} />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(mockOnClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when disabled prop is true', () => {
    render(<GenerateButton onClick={mockOnClick} disabled={true} />);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });

  it('is not disabled when disabled prop is false', () => {
    render(<GenerateButton onClick={mockOnClick} disabled={false} />);
    const button = screen.getByRole('button');
    expect(button).not.toBeDisabled();
  });

  it('is disabled when isGenerating is true', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={true} />);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });

  it('shows "Generating..." text when isGenerating is true', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={true} />);
    expect(screen.getByText('Generating...')).toBeInTheDocument();
  });

  it('does not show default label when isGenerating is true', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={true} />);
    expect(screen.queryByText('Generate Images')).not.toBeInTheDocument();
  });

  it('does not call onClick when disabled', async () => {
    const user = userEvent.setup();
    render(<GenerateButton onClick={mockOnClick} disabled={true} />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(mockOnClick).not.toHaveBeenCalled();
  });

  it('does not call onClick when isGenerating is true', async () => {
    const user = userEvent.setup();
    render(<GenerateButton onClick={mockOnClick} isGenerating={true} />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(mockOnClick).not.toHaveBeenCalled();
  });

  it('has aria-busy attribute when isGenerating is true', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={true} />);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('does not have aria-busy=true when isGenerating is false', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={false} />);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-busy', 'false');
  });

  it('has correct aria-label based on state', () => {
    const { rerender } = render(<GenerateButton onClick={mockOnClick} />);
    let button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-label', 'Generate Images');

    rerender(<GenerateButton onClick={mockOnClick} isGenerating={true} />);
    button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-label', 'Generating...');
  });

  it('shows spinner when isGenerating is true', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={true} />);
    // Spinner is an SVG with specific class
    const spinner = screen.getByRole('button').querySelector('svg');
    expect(spinner).toBeInTheDocument();
  });

  it('does not show spinner when isGenerating is false', () => {
    render(<GenerateButton onClick={mockOnClick} isGenerating={false} />);
    const spinner = screen.getByRole('button').querySelector('svg');
    expect(spinner).not.toBeInTheDocument();
  });

  it('is a button element with type="button"', () => {
    render(<GenerateButton onClick={mockOnClick} />);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('type', 'button');
  });

  it('handles simultaneous disabled and isGenerating props', () => {
    render(<GenerateButton onClick={mockOnClick} disabled={true} isGenerating={true} />);
    const button = screen.getByRole('button');

    expect(button).toBeDisabled();
    expect(screen.getByText('Generating...')).toBeInTheDocument();
  });
});
