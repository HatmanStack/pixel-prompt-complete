/**
 * ModelColumn tests.
 *
 * The main generation surface, previously at 0% coverage. Child components
 * are stubbed so these assert ModelColumn's own decisions: what it renders,
 * what it hides, and which handler a click reaches.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockUseIteration = vi.fn();

vi.mock('../../../../src/hooks/useIteration', () => ({
  useIteration: (model: string) => mockUseIteration(model),
}));

vi.mock('../../../../src/components/generation/IterationCard', () => ({
  IterationCard: ({
    iteration,
    onExpand,
  }: {
    iteration: { index: number };
    onExpand: () => void;
  }) => (
    <button data-testid={`card-${iteration.index}`} onClick={onExpand}>
      iteration {iteration.index}
    </button>
  ),
}));

vi.mock('../../../../src/components/generation/IterationInput', () => ({
  IterationInput: () => <div data-testid="iteration-input" />,
}));

vi.mock('../../../../src/components/generation/OutpaintControls', () => ({
  OutpaintControls: () => <div data-testid="outpaint-controls" />,
}));

import { ModelColumn } from '../../../../src/components/generation/ModelColumn';
import { useAppStore } from '../../../../src/stores/useAppStore';
import type { Iteration, ModelColumn as ModelColumnType } from '../../../../src/types';

function iteration(index: number, overrides: Partial<Iteration> = {}): Iteration {
  return {
    index,
    status: 'completed',
    prompt: `prompt ${index}`,
    imageUrl: `https://cdn.test/${index}.png`,
    ...overrides,
  };
}

function column(overrides: Partial<ModelColumnType> = {}): ModelColumnType {
  return {
    name: 'gemini',
    enabled: true,
    status: 'completed',
    iterations: [],
    ...overrides,
  };
}

function renderColumn(props: Partial<React.ComponentProps<typeof ModelColumn>> = {}) {
  const onToggleSelect = vi.fn();
  const onFocusToggle = vi.fn();
  const onImageExpand = vi.fn();
  render(
    <ModelColumn
      model="gemini"
      column={column()}
      isSelected={false}
      onToggleSelect={onToggleSelect}
      onFocusToggle={onFocusToggle}
      onImageExpand={onImageExpand}
      {...props}
    />,
  );
  return { onToggleSelect, onFocusToggle, onImageExpand };
}

describe('ModelColumn', () => {
  beforeEach(() => {
    mockUseIteration.mockReset();
    mockUseIteration.mockReturnValue({ isAtLimit: false });
    useAppStore.setState({ currentSession: null });
  });

  describe('disabled model', () => {
    it('shows the disabled state instead of iterations', () => {
      renderColumn({ column: column({ enabled: false, iterations: [iteration(0)] }) });
      expect(screen.getByText(/is not enabled/)).toBeInTheDocument();
      expect(screen.queryByTestId('card-0')).not.toBeInTheDocument();
    });

    it('offers no way to spend on a model that cannot run', () => {
      renderColumn({ column: column({ enabled: false }) });
      expect(screen.queryByTestId('iteration-input')).not.toBeInTheDocument();
      expect(screen.queryByTestId('outpaint-controls')).not.toBeInTheDocument();
    });
  });

  describe('iterations', () => {
    it('tells the user nothing has been generated yet', () => {
      renderColumn();
      expect(screen.getByText('No images yet')).toBeInTheDocument();
    });

    it('renders every iteration', () => {
      renderColumn({ column: column({ iterations: [iteration(0), iteration(1), iteration(2)] }) });
      expect(screen.getAllByRole('listitem')).toHaveLength(3);
    });

    it('shows the count against the iteration limit', () => {
      renderColumn({ column: column({ iterations: [iteration(0), iteration(1)] }) });
      expect(screen.getByText(/^2\//)).toBeInTheDocument();
    });

    it('passes the expanded iteration back to the caller', async () => {
      const { onImageExpand } = renderColumn({
        column: column({ iterations: [iteration(0), iteration(1)] }),
      });
      await userEvent.click(screen.getByTestId('card-1'));
      expect(onImageExpand).toHaveBeenCalledWith('gemini', expect.objectContaining({ index: 1 }));
    });
  });

  describe('compressed mode', () => {
    it('shows only the most recent iteration', () => {
      renderColumn({
        isCompressed: true,
        column: column({ iterations: [iteration(0), iteration(1), iteration(2)] }),
      });
      expect(screen.getAllByRole('listitem')).toHaveLength(1);
      expect(screen.getByTestId('card-2')).toBeInTheDocument();
      expect(screen.queryByTestId('card-0')).not.toBeInTheDocument();
    });

    it('keeps the refinement input available', () => {
      renderColumn({ isCompressed: true, column: column({ iterations: [iteration(0)] }) });
      expect(screen.getByTestId('iteration-input')).toBeInTheDocument();
    });

    it('hides outpaint controls and the selection checkbox', () => {
      renderColumn({ isCompressed: true, column: column({ iterations: [iteration(0)] }) });
      expect(screen.queryByTestId('outpaint-controls')).not.toBeInTheDocument();
      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    });
  });

  describe('iteration limit', () => {
    it('hides the input once the model is at its limit', () => {
      mockUseIteration.mockReturnValue({ isAtLimit: true });
      renderColumn({ column: column({ iterations: [iteration(0)] }) });
      expect(screen.queryByTestId('iteration-input')).not.toBeInTheDocument();
    });

    it('still allows outpainting at the limit', () => {
      mockUseIteration.mockReturnValue({ isAtLimit: true });
      renderColumn({ column: column({ iterations: [iteration(0)] }) });
      expect(screen.getByTestId('outpaint-controls')).toBeInTheDocument();
    });
  });

  describe('focus and selection', () => {
    it('toggles focus when the header is clicked', async () => {
      const { onFocusToggle } = renderColumn();
      await userEvent.click(screen.getByRole('button', { name: /Expand Gemini column/i }));
      expect(onFocusToggle).toHaveBeenCalled();
    });

    it('toggles focus from the keyboard', async () => {
      const { onFocusToggle } = renderColumn();
      screen.getByRole('button', { name: /Expand Gemini column/i }).focus();
      await userEvent.keyboard('{Enter}');
      expect(onFocusToggle).toHaveBeenCalled();
    });

    it('reflects the expanded state for assistive tech', () => {
      renderColumn({ isFocused: true });
      expect(screen.getByRole('button', { name: /Collapse Gemini column/i })).toHaveAttribute(
        'aria-expanded',
        'true',
      );
    });

    it('selecting the column does not also collapse it', async () => {
      // The checkbox sits inside the clickable header; without
      // stopPropagation, ticking it would fold the column away underneath.
      const { onToggleSelect, onFocusToggle } = renderColumn();
      await userEvent.click(screen.getByRole('checkbox'));
      expect(onToggleSelect).toHaveBeenCalled();
      expect(onFocusToggle).not.toHaveBeenCalled();
    });
  });
});
