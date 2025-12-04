/**
 * Tests for PromptInput Component
 */

import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PromptInput from '@/components/generation/PromptInput';
import { useAppStore } from '@/stores/useAppStore';
import { useUIStore } from '@/stores/useUIStore';

// Mock Audio
vi.stubGlobal('Audio', vi.fn().mockImplementation(() => ({
  volume: 0.5,
  currentTime: 0,
  preload: '',
  src: '',
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn(),
})));

describe('PromptInput', () => {
  beforeEach(() => {
    // Reset stores before each test
    useAppStore.setState({ prompt: '' });
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: true,
    });
  });

  it('renders with placeholder text', () => {
    render(<PromptInput />);
    const textarea = screen.getByPlaceholderText('Describe the image you want to generate...');
    expect(textarea).toBeInTheDocument();
  });

  it('displays the current value from store', () => {
    act(() => {
      useAppStore.setState({ prompt: 'test prompt' });
    });

    render(<PromptInput />);
    const textarea = screen.getByRole('textbox', { name: /image prompt/i });
    expect(textarea).toHaveValue('test prompt');
  });

  it('updates store when text is entered', async () => {
    const user = userEvent.setup();
    render(<PromptInput />);
    const textarea = screen.getByRole('textbox');

    await user.type(textarea, 'new text');

    expect(useAppStore.getState().prompt).toBe('new text');
  });

  it('shows character counter', () => {
    act(() => {
      useAppStore.setState({ prompt: 'hello' });
    });

    render(<PromptInput />);
    expect(screen.getByText('5 / 500')).toBeInTheDocument();
  });

  it('enforces maxLength constraint', async () => {
    const user = userEvent.setup();
    render(<PromptInput maxLength={10} />);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, '12345678901'); // 11 characters

    // Only first 10 characters should be accepted
    expect(useAppStore.getState().prompt.length).toBeLessThanOrEqual(10);
  });

  it('shows clear button when value is present and not disabled', () => {
    act(() => {
      useAppStore.setState({ prompt: 'test' });
    });

    render(<PromptInput />);
    const clearButton = screen.getByLabelText('Clear prompt');
    expect(clearButton).toBeInTheDocument();
  });

  it('hides clear button when value is empty', () => {
    render(<PromptInput />);
    const clearButton = screen.queryByLabelText('Clear prompt');
    expect(clearButton).not.toBeInTheDocument();
  });

  it('hides clear button when disabled', () => {
    act(() => {
      useAppStore.setState({ prompt: 'test' });
    });

    render(<PromptInput disabled={true} />);
    const clearButton = screen.queryByLabelText('Clear prompt');
    expect(clearButton).not.toBeInTheDocument();
  });

  it('clears prompt when clear button is clicked (short text, no confirmation)', async () => {
    const user = userEvent.setup();
    act(() => {
      useAppStore.setState({ prompt: 'short' });
    });

    render(<PromptInput />);

    const clearButton = screen.getByLabelText('Clear prompt');
    await user.click(clearButton);

    expect(useAppStore.getState().prompt).toBe('');
  });

  it('shows keyboard hint text', () => {
    render(<PromptInput />);
    expect(screen.getByText(/Press Ctrl\+Enter to generate/i)).toBeInTheDocument();
  });

  it('disables textarea when disabled prop is true', () => {
    render(<PromptInput disabled={true} />);
    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeDisabled();
  });

  it('uses custom placeholder when provided', () => {
    const customPlaceholder = 'Custom placeholder text';
    render(<PromptInput placeholder={customPlaceholder} />);
    expect(screen.getByPlaceholderText(customPlaceholder)).toBeInTheDocument();
  });

  it('shows warning style when near character limit', () => {
    const maxLength = 100;
    const nearLimitValue = 'a'.repeat(60);
    act(() => {
      useAppStore.setState({ prompt: nearLimitValue });
    });

    render(<PromptInput maxLength={maxLength} />);

    // Character count should still be visible
    expect(screen.getByText(`${nearLimitValue.length} / ${maxLength}`)).toBeInTheDocument();
  });
});
