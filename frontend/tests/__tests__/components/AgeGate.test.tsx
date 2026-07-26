/**
 * The 18+ gate.
 *
 * The interesting case is not the modal's markup, it is the wiring: the
 * backend refuses with a machine-readable code, and the panel has to recognise
 * it and open the gate rather than showing the user a raw error string.
 *
 * That wiring was broken when first written -- see the error-code contract
 * test in tests/__tests__/api/client.test.ts, which pins the other half.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGenerateSession = vi.fn();
const mockGetSessionStatus = vi.fn();
const mockShowError = vi.fn();

vi.mock('../../../src/api/client', () => ({
  generateSession: (...a: unknown[]) => mockGenerateSession(...a),
  getSessionStatus: (...a: unknown[]) => mockGetSessionStatus(...a),
}));

vi.mock('../../../src/api/config', () => ({
  CAPTCHA_ENABLED: false,
  TURNSTILE_SITE_KEY: 'k',
  API_BASE_URL: 'https://api.test',
  API_ROUTES: { PRICING: '/pricing' },
}));

vi.mock('../../../src/stores/useToastStore', () => ({
  useToast: () => ({
    error: mockShowError,
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

vi.mock('../../../src/hooks/useSound', () => ({
  useSound: () => ({ playSound: vi.fn() }),
}));

vi.mock('../../../src/components/generation/PromptInput', () => ({
  __esModule: true,
  default: () => <div />,
}));
vi.mock('../../../src/components/generation/PromptEnhancer', () => ({
  __esModule: true,
  default: () => <div />,
}));
vi.mock('../../../src/components/features/generation/RandomPromptButton', () => ({
  __esModule: true,
  default: () => <div />,
}));
vi.mock('../../../src/components/generation/GenerateButton', () => ({
  __esModule: true,
  default: ({ onClick }: { onClick: () => void }) => <button onClick={onClick}>Generate</button>,
}));
vi.mock('../../../src/components/generation/ModelColumn', () => ({
  ModelColumn: () => <div />,
}));
vi.mock('../../../src/components/generation/MultiIterateInput', () => ({
  MultiIterateInput: () => <div />,
}));
vi.mock('../../../src/components/generation/PromptHistory', () => ({
  PromptHistory: () => <div />,
}));
vi.mock('../../../src/components/gallery/GalleryBrowser', () => ({
  __esModule: true,
  default: () => <div />,
}));
vi.mock('../../../src/components/features/generation/ImageModal', () => ({
  ImageModal: () => <div />,
}));
vi.mock('../../../src/components/generation/CompareModal', () => ({
  CompareModal: () => <div />,
}));
vi.mock('../../../src/components/features/CaptchaWidget', () => ({
  CaptchaWidget: () => <div />,
}));

import { GenerationPanel } from '../../../src/components/generation/GenerationPanel';
import { useAppStore } from '../../../src/stores/useAppStore';

function ageError() {
  return Object.assign(new Error('AGE_VERIFICATION_REQUIRED'), {
    status: 403,
    code: 'AGE_VERIFICATION_REQUIRED',
  });
}

const FINISHED = {
  sessionId: 's1',
  status: 'completed',
  prompt: 'a cat',
  createdAt: 'now',
  updatedAt: 'now',
  models: {},
};

describe('age gate', () => {
  beforeEach(() => {
    mockGenerateSession.mockReset();
    mockShowError.mockReset();
    mockGetSessionStatus.mockReset();
    mockGetSessionStatus.mockResolvedValue({ ...FINISHED, status: 'in_progress' });
    useAppStore.setState({ prompt: 'a cat', currentSession: null, isGenerating: false });
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  async function generate() {
    await userEvent.click(screen.getByRole('button', { name: 'Generate' }));
  }

  it('opens the gate instead of showing a raw error code', async () => {
    mockGenerateSession.mockRejectedValue(ageError());
    render(<GenerationPanel />);
    await generate();

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    // The user has not failed at anything, they have not been asked yet.
    expect(mockShowError).not.toHaveBeenCalled();
  });

  it('does not send an affirmation before the user gives one', async () => {
    mockGenerateSession.mockRejectedValue(ageError());
    render(<GenerationPanel />);
    await generate();

    await waitFor(() => expect(mockGenerateSession).toHaveBeenCalled());
    expect(mockGenerateSession.mock.calls[0][2]).toBeFalsy();
  });

  it('sends the affirmation on the retry after the user confirms', async () => {
    mockGenerateSession.mockRejectedValueOnce(ageError());
    render(<GenerationPanel />);
    await generate();

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    mockGenerateSession.mockResolvedValue({ sessionId: 's1', session: FINISHED });
    await userEvent.click(screen.getByRole('button', { name: /18 or older/i }));
    await generate();

    await waitFor(() => expect(mockGenerateSession).toHaveBeenCalledTimes(2));
    expect(mockGenerateSession.mock.calls[1][2]).toBe(true);
  });

  it('closes and refuses when the user says they are under 18', async () => {
    mockGenerateSession.mockRejectedValue(ageError());
    render(<GenerationPanel />);
    await generate();

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /under 18/i }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mockShowError).toHaveBeenCalled();
    expect(String(mockShowError.mock.calls[0][0])).toMatch(/18 or over/i);
  });

  it('keeps the prompt so confirming resumes where the user was', async () => {
    mockGenerateSession.mockRejectedValue(ageError());
    render(<GenerationPanel />);
    await generate();

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(useAppStore.getState().prompt).toBe('a cat');
  });

  it('does not open the gate for an unrelated 403', async () => {
    mockGenerateSession.mockRejectedValue(
      Object.assign(new Error('CAPTCHA_REQUIRED'), { status: 403, code: 'CAPTCHA_REQUIRED' }),
    );
    render(<GenerationPanel />);
    await generate();

    await waitFor(() => expect(mockShowError).toHaveBeenCalled());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
