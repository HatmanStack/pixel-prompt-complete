/**
 * GenerationPanel tests.
 *
 * The main orchestrator, previously at 0% across 463 lines. These focus on
 * the paths that carry money or user-visible failure: what happens with the
 * generate response, and how each backend refusal is surfaced.
 *
 * Every child is stubbed. The point is the panel's own decisions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGenerateSession = vi.fn();
const mockGetSessionStatus = vi.fn();
const mockShowError = vi.fn();

vi.mock('../../../../src/api/client', () => ({
  generateSession: (...a: unknown[]) => mockGenerateSession(...a),
  getSessionStatus: (...a: unknown[]) => mockGetSessionStatus(...a),
}));

vi.mock('../../../../src/api/config', () => ({
  CAPTCHA_ENABLED: false,
  TURNSTILE_SITE_KEY: 'k',
  API_BASE_URL: 'https://api.test',
  API_ROUTES: { PRICING: '/pricing' },
}));

vi.mock('../../../../src/stores/useToastStore', () => ({
  // The panel destructures `const { error: showError } = useToast()`.
  useToast: () => ({
    error: mockShowError,
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

vi.mock('../../../../src/hooks/useSound', () => ({
  useSound: () => ({ playSound: vi.fn() }),
}));

// Children are not under test here. Factories are inlined because vi.mock is
// hoisted above any helper defined in this file.
vi.mock('../../../../src/components/generation/PromptInput', () => ({
  __esModule: true,
  default: () => <div data-testid="prompt-input" />,
}));
vi.mock('../../../../src/components/generation/PromptEnhancer', () => ({
  __esModule: true,
  default: () => <div data-testid="prompt-enhancer" />,
}));
vi.mock('../../../../src/components/generation/RandomPromptButton', () => ({
  __esModule: true,
  default: () => <div data-testid="random-prompt" />,
}));
vi.mock('../../../../src/components/generation/GenerateButton', () => ({
  __esModule: true,
  default: ({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>
      Generate
    </button>
  ),
}));
vi.mock('../../../../src/components/generation/ModelColumn', () => ({
  ModelColumn: ({ model }: { model: string }) => <div data-testid={`column-${model}`} />,
}));
vi.mock('../../../../src/components/generation/MultiIterateInput', () => ({
  MultiIterateInput: () => <div />,
}));
vi.mock('../../../../src/components/generation/PromptHistory', () => ({
  PromptHistory: () => <div />,
}));
vi.mock('../../../../src/components/gallery/GalleryBrowser', () => ({
  __esModule: true,
  default: () => <div data-testid="gallery" />,
}));
vi.mock('../../../../src/components/generation/ImageModal', () => ({
  ImageModal: () => <div />,
}));
vi.mock('../../../../src/components/generation/CompareModal', () => ({
  CompareModal: () => <div />,
}));
vi.mock('../../../../src/components/gating/CaptchaWidget', () => ({
  CaptchaWidget: () => <div data-testid="captcha" />,
}));

import { GenerationPanel } from '../../../../src/components/generation/GenerationPanel';
import { useAppStore } from '../../../../src/stores/useAppStore';

const FINISHED = {
  sessionId: 's1',
  status: 'completed',
  prompt: 'a cat',
  createdAt: 'now',
  updatedAt: 'now',
  models: {},
};

function apiError(status: number, message: string) {
  return Object.assign(new Error(message), { status, message, error: 'ERR' });
}

describe('GenerationPanel', () => {
  beforeEach(() => {
    mockGenerateSession.mockReset();
    mockShowError.mockReset();
    mockGetSessionStatus.mockReset();
    mockGetSessionStatus.mockResolvedValue({ ...FINISHED, status: 'in_progress' });
    useAppStore.setState({
      prompt: 'a cat',
      currentSession: null,
      isGenerating: false,
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  async function clickGenerate() {
    render(<GenerationPanel />);
    await userEvent.click(screen.getByRole('button', { name: 'Generate' }));
  }

  describe('successful generation', () => {
    it('uses the session returned by /generate', async () => {
      mockGenerateSession.mockResolvedValue({ sessionId: 's1', session: FINISHED });
      await clickGenerate();
      await waitFor(() => expect(useAppStore.getState().currentSession?.sessionId).toBe('s1'));
    });

    it('stops generating once a terminal session arrives', async () => {
      mockGenerateSession.mockResolvedValue({ sessionId: 's1', session: FINISHED });
      await clickGenerate();
      await waitFor(() => expect(useAppStore.getState().isGenerating).toBe(false));
    });

    it('keeps generating when the session is not terminal', async () => {
      // A model may still be running: as_completed's timeout does not cancel
      // in-flight futures, so polling has to continue or late images are lost.
      mockGenerateSession.mockResolvedValue({
        sessionId: 's1',
        session: { ...FINISHED, status: 'in_progress' },
      });
      await clickGenerate();
      await waitFor(() => expect(useAppStore.getState().currentSession?.sessionId).toBe('s1'));
      expect(useAppStore.getState().isGenerating).toBe(true);
    });

    it('falls back to polling when no session is attached', async () => {
      // The server attaches a session only when it is terminal. Without one,
      // the panel must keep generating so the poller picks up the result,
      // otherwise the images land with nobody listening.
      mockGenerateSession.mockResolvedValue({ sessionId: 's1' });
      await clickGenerate();

      await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalledWith('s1'));
      expect(useAppStore.getState().isGenerating).toBe(true);
    });

    it('does not poll when the response already carried a terminal session', async () => {
      mockGenerateSession.mockResolvedValue({ sessionId: 's1', session: FINISHED });
      await clickGenerate();

      await waitFor(() => expect(useAppStore.getState().isGenerating).toBe(false));
      expect(mockGetSessionStatus).not.toHaveBeenCalled();
    });
  });

  describe('the 202 async-dispatch response', () => {
    // This is now the DEFAULT server response, not a degraded one. /generate
    // answers as soon as the session exists and hands the provider dispatch to
    // a worker invocation, because the previous ~70s dispatch ran behind a 30s
    // API Gateway ceiling and the caller got a 504 for work that completed and
    // was billed anyway.
    //
    // The panel needed no change for this -- the branch already existed for the
    // read-back-failed case. These tests exist because a path that carries
    // every generation deserves to be pinned by something other than luck.
    const ACCEPTED = {
      sessionId: 's1',
      prompt: 'a cat',
      models: { gemini: { status: 'pending' }, nova: { status: 'pending' } },
    };

    beforeEach(() => {
      // Hold the first poll open. The placeholder is what the user sees for
      // the whole dispatch, and the outer beforeEach resolves /status
      // immediately, which would overwrite it before it could be inspected.
      mockGetSessionStatus.mockReturnValue(new Promise(() => {}));
      mockGenerateSession.mockResolvedValue(ACCEPTED);
    });

    it('builds a placeholder session when the response carries no session', async () => {
      await clickGenerate();

      await waitFor(() => expect(useAppStore.getState().currentSession).not.toBeNull());
      const session = useAppStore.getState().currentSession;
      expect(session?.sessionId).toBe('s1');
      expect(session?.status).toBe('pending');
    });

    it('starts polling /status', async () => {
      await clickGenerate();

      await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalledWith('s1'));
    });

    it('stays in the generating state so late images are not lost', async () => {
      await clickGenerate();

      await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalled());
      expect(useAppStore.getState().isGenerating).toBe(true);
    });

    it('gives the placeholder a column for every model', async () => {
      // The columns render before any provider has run. Without them the user
      // sees an empty panel for the whole generation.
      await clickGenerate();

      await waitFor(() => expect(useAppStore.getState().currentSession).not.toBeNull());
      const columns = Object.values(useAppStore.getState().currentSession?.models ?? {});
      expect(columns.length).toBeGreaterThan(0);
      for (const column of columns) {
        expect(column).toMatchObject({ iterations: [] });
      }
    });

    it('does not mistake the pending models map for a session', async () => {
      // `models` is a sibling of `session`, not a substitute for it. Reading it
      // as one would show four completed-looking columns with no images.
      await clickGenerate();

      await waitFor(() => expect(useAppStore.getState().currentSession).not.toBeNull());
      expect(useAppStore.getState().currentSession?.status).not.toBe('completed');
    });
  });

  describe('backend refusals', () => {
    it('surfaces a quota rejection', async () => {
      mockGenerateSession.mockRejectedValue(apiError(429, 'Quota exceeded for free tier'));
      await clickGenerate();
      await waitFor(() => expect(mockShowError).toHaveBeenCalled());
      expect(String(mockShowError.mock.calls[0][0])).toMatch(/Rate limit/i);
    });

    it('surfaces the content filter refusal', async () => {
      mockGenerateSession.mockRejectedValue(apiError(400, 'content filter blocked'));
      await clickGenerate();
      await waitFor(() => expect(mockShowError).toHaveBeenCalled());
      expect(String(mockShowError.mock.calls[0][0])).toMatch(/inappropriate/i);
    });

    it('surfaces the spend ceiling refusal rather than failing silently', async () => {
      mockGenerateSession.mockRejectedValue(
        apiError(503, 'the daily generation budget has been reached'),
      );
      await clickGenerate();
      await waitFor(() => expect(mockShowError).toHaveBeenCalled());
      expect(String(mockShowError.mock.calls[0][0])).toMatch(/budget/i);
    });

    it('surfaces an insufficient-credits refusal', async () => {
      mockGenerateSession.mockRejectedValue(
        apiError(402, 'Not enough credits remaining on the paid plan.'),
      );
      await clickGenerate();
      await waitFor(() => expect(mockShowError).toHaveBeenCalled());
      expect(String(mockShowError.mock.calls[0][0])).toMatch(/credits/i);
    });

    it('stops the generating state on any failure', async () => {
      mockGenerateSession.mockRejectedValue(apiError(500, 'boom'));
      await clickGenerate();
      await waitFor(() => expect(useAppStore.getState().isGenerating).toBe(false));
    });

    it('does not leave a half-built session behind after a failure', async () => {
      mockGenerateSession.mockRejectedValue(apiError(500, 'boom'));
      await clickGenerate();
      await waitFor(() => expect(mockShowError).toHaveBeenCalled());
      expect(useAppStore.getState().currentSession).toBeNull();
    });

    it('rejects a response with no session id', async () => {
      mockGenerateSession.mockResolvedValue({});
      await clickGenerate();
      await waitFor(() => expect(mockShowError).toHaveBeenCalled());
      expect(useAppStore.getState().isGenerating).toBe(false);
    });
  });
});
