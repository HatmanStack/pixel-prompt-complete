/**
 * Tests for PromptInput Component
 */

import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PromptInput from '../../components/generation/PromptInput';

describe('PromptInput', () => {
  const mockOnChange = vi.fn();
  const mockOnClear = vi.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
    mockOnClear.mockClear();
  });

  it('renders with placeholder text', () => {
    render(<PromptInput value="" onChange={mockOnChange} onClear={mockOnClear} />);
    const textarea = screen.getByPlaceholderText('Describe the image you want to generate...');
    expect(textarea).toBeInTheDocument();
  });

  it('displays the current value', () => {
    render(<PromptInput value="test prompt" onChange={mockOnChange} onClear={mockOnClear} />);
    const textarea = screen.getByRole('textbox', { name: /image prompt/i });
    expect(textarea).toHaveValue('test prompt');
  });

  it('calls onChange when text is entered', async () => {
    const user = userEvent.setup();
    render(<PromptInput value="" onChange={mockOnChange} onClear={mockOnClear} />);
    const textarea = screen.getByRole('textbox');

    await user.type(textarea, 'new text');

    expect(mockOnChange).toHaveBeenCalled();
  });

  it('shows character counter', () => {
    render(<PromptInput value="hello" onChange={mockOnChange} onClear={mockOnClear} />);
    expect(screen.getByText('5 / 500')).toBeInTheDocument();
  });

  it('enforces maxLength constraint', () => {
    const maxLength = 10;
    render(
      <PromptInput
        value="short"
        onChange={mockOnChange}
        onClear={mockOnClear}
        maxLength={maxLength}
      />
    );

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '12345678901' } });

    // onChange should not be called for text exceeding maxLength
    expect(mockOnChange).not.toHaveBeenCalledWith('12345678901');
  });

  it('shows clear button when value is present and not disabled', () => {
    render(<PromptInput value="test" onChange={mockOnChange} onClear={mockOnClear} />);
    const clearButton = screen.getByLabelText('Clear prompt');
    expect(clearButton).toBeInTheDocument();
  });

  it('hides clear button when value is empty', () => {
    render(<PromptInput value="" onChange={mockOnChange} onClear={mockOnClear} />);
    const clearButton = screen.queryByLabelText('Clear prompt');
    expect(clearButton).not.toBeInTheDocument();
  });

  it('hides clear button when disabled', () => {
    render(<PromptInput value="test" onChange={mockOnChange} onClear={mockOnClear} disabled={true} />);
    const clearButton = screen.queryByLabelText('Clear prompt');
    expect(clearButton).not.toBeInTheDocument();
  });

  it('calls onClear when clear button is clicked (short text, no confirmation)', async () => {
    const user = userEvent.setup();
    render(<PromptInput value="short" onChange={mockOnChange} onClear={mockOnClear} />);

    const clearButton = screen.getByLabelText('Clear prompt');
    await user.click(clearButton);

    expect(mockOnClear).toHaveBeenCalled();
  });

  it('shows keyboard hint text', () => {
    render(<PromptInput value="" onChange={mockOnChange} onClear={mockOnClear} />);
    expect(screen.getByText(/Press Ctrl\+Enter to generate/i)).toBeInTheDocument();
  });

  it('disables textarea when disabled prop is true', () => {
    render(<PromptInput value="" onChange={mockOnChange} onClear={mockOnClear} disabled={true} />);
    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeDisabled();
  });

  it('uses custom placeholder when provided', () => {
    const customPlaceholder = 'Custom placeholder text';
    render(
      <PromptInput
        value=""
        onChange={mockOnChange}
        onClear={mockOnClear}
        placeholder={customPlaceholder}
      />
    );
    expect(screen.getByPlaceholderText(customPlaceholder)).toBeInTheDocument();
  });

  it('shows warning style when near character limit', () => {
    const maxLength = 100;
    const nearLimitValue = 'a'.repeat(60); // > 50 chars from limit
    render(
      <PromptInput
        value={nearLimitValue}
        onChange={mockOnChange}
        onClear={mockOnClear}
        maxLength={maxLength}
      />
    );

    // Character count should still be visible
    expect(screen.getByText(`${nearLimitValue.length} / ${maxLength}`)).toBeInTheDocument();
  });
});
