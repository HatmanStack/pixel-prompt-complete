/**
 * Tests for CompareModal component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CompareModal } from '../../../src/components/generation/CompareModal';
import type { Session, ModelName } from '../../../src/types/api';

function createMockSession(
  models: ModelName[] = ['gemini', 'nova'],
): Session {
  const modelColumns: Record<string, unknown> = {};
  for (const model of ['gemini', 'nova', 'openai', 'firefly'] as ModelName[]) {
    modelColumns[model] = {
      name: model,
      enabled: models.includes(model),
      status: 'completed',
      iterations: models.includes(model)
        ? [
            {
              index: 1,
              status: 'completed',
              prompt: `Prompt for ${model} iter 1`,
              imageUrl: `https://cdn.example.com/${model}-1.png`,
            },
            {
              index: 2,
              status: 'completed',
              prompt: `Prompt for ${model} iter 2`,
              imageUrl: `https://cdn.example.com/${model}-2.png`,
            },
          ]
        : [],
    };
  }

  return {
    sessionId: 'test-session-123',
    status: 'completed',
    prompt: 'Test prompt',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    models: modelColumns,
  } as unknown as Session;
}

describe('CompareModal', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders selected models with model names', () => {
    render(
      <CompareModal
        models={['gemini', 'nova']}
        session={createMockSession(['gemini', 'nova'])}
        onClose={onClose}
      />,
    );

    expect(screen.getByText('Gemini')).toBeDefined();
    expect(screen.getByText('Nova Canvas')).toBeDefined();
  });

  it('shows latest iteration by default', () => {
    render(
      <CompareModal
        models={['gemini', 'nova']}
        session={createMockSession(['gemini', 'nova'])}
        onClose={onClose}
      />,
    );

    // Latest iteration images (index 2)
    const images = screen.getAllByRole('img');
    expect(images[0]).toHaveAttribute('src', 'https://cdn.example.com/gemini-2.png');
    expect(images[1]).toHaveAttribute('src', 'https://cdn.example.com/nova-2.png');
  });

  it('iteration picker changes displayed image', () => {
    render(
      <CompareModal
        models={['gemini', 'nova']}
        session={createMockSession(['gemini', 'nova'])}
        onClose={onClose}
      />,
    );

    // Find the iteration select for gemini and change to iteration 1
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: '1' } });

    const images = screen.getAllByRole('img');
    expect(images[0]).toHaveAttribute('src', 'https://cdn.example.com/gemini-1.png');
  });

  it('ESC key closes modal', () => {
    render(
      <CompareModal
        models={['gemini', 'nova']}
        session={createMockSession(['gemini', 'nova'])}
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalled();
  });

  it('backdrop click closes modal', () => {
    render(
      <CompareModal
        models={['gemini', 'nova']}
        session={createMockSession(['gemini', 'nova'])}
        onClose={onClose}
      />,
    );

    // Click the backdrop (the outer overlay div)
    const backdrop = screen.getByTestId('compare-backdrop');
    fireEvent.click(backdrop);

    expect(onClose).toHaveBeenCalled();
  });
});
