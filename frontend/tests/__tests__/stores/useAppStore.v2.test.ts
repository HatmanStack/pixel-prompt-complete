/**
 * Tests for useAppStore - Session-based state (v2)
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '../../../src/stores/useAppStore';
import type { Session, SessionPreview, ModelName, Iteration, ModelColumn } from '../../../src/types';

// Helper to create mock Session
const createMockSession = (overrides: Partial<Session> = {}): Session => ({
  sessionId: 'test-session-123',
  status: 'in_progress',
  prompt: 'test prompt',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
  models: {
    flux: createMockModelColumn('flux'),
    recraft: createMockModelColumn('recraft'),
    gemini: createMockModelColumn('gemini'),
    openai: createMockModelColumn('openai'),
  },
  ...overrides,
});

// Helper to create mock ModelColumn
const createMockModelColumn = (
  name: ModelName,
  overrides: Partial<ModelColumn> = {}
): ModelColumn => ({
  name,
  enabled: true,
  status: 'pending',
  iterations: [],
  ...overrides,
});

// Helper to create mock Iteration
const createMockIteration = (
  index: number,
  overrides: Partial<Iteration> = {}
): Iteration => ({
  index,
  status: 'completed',
  prompt: `iteration ${index} prompt`,
  imageUrl: `https://example.com/image-${index}.png`,
  ...overrides,
});

// Helper to create mock SessionPreview
const createMockSessionPreview = (overrides: Partial<SessionPreview> = {}): SessionPreview => ({
  sessionId: 'session-1',
  prompt: 'test prompt',
  thumbnail: 'https://example.com/thumb.png',
  totalIterations: 4,
  createdAt: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('useAppStore - Session-based state', () => {
  beforeEach(() => {
    // Reset store to initial state
    useAppStore.setState({
      currentSession: null,
      isGenerating: false,
      prompt: '',
      selectedModels: new Set(),
      isMultiSelectMode: false,
      sessions: [],
      selectedGallerySession: null,
      iterationWarnings: {
        flux: false,
        recraft: false,
        gemini: false,
        openai: false,
      },
      // Legacy state
      currentJob: null,
      generatedImages: Array(9).fill(null),
      selectedGallery: null,
      galleries: [],
      currentView: 'generation',
    });
  });

  describe('session actions', () => {
    it('setCurrentSession sets session', () => {
      const session = createMockSession();
      useAppStore.getState().setCurrentSession(session);

      expect(useAppStore.getState().currentSession).toEqual(session);
    });

    it('setCurrentSession can clear session', () => {
      useAppStore.getState().setCurrentSession(createMockSession());
      useAppStore.getState().setCurrentSession(null);

      expect(useAppStore.getState().currentSession).toBeNull();
    });

    it('updateModelIteration adds new iteration', () => {
      const session = createMockSession();
      useAppStore.getState().setCurrentSession(session);

      const iteration = createMockIteration(0);
      useAppStore.getState().updateModelIteration('flux', iteration);

      const state = useAppStore.getState();
      expect(state.currentSession?.models.flux.iterations).toHaveLength(1);
      expect(state.currentSession?.models.flux.iterations[0]).toEqual(iteration);
    });

    it('updateModelIteration updates existing iteration', () => {
      const session = createMockSession({
        models: {
          ...createMockSession().models,
          flux: createMockModelColumn('flux', {
            iterations: [createMockIteration(0, { status: 'loading' })],
          }),
        },
      });
      useAppStore.getState().setCurrentSession(session);

      const updatedIteration = createMockIteration(0, { status: 'completed' });
      useAppStore.getState().updateModelIteration('flux', updatedIteration);

      const state = useAppStore.getState();
      expect(state.currentSession?.models.flux.iterations[0].status).toBe('completed');
    });

    it('resetSession clears session state', () => {
      useAppStore.getState().setCurrentSession(createMockSession());
      useAppStore.getState().setIsGenerating(true);
      useAppStore.getState().toggleModelSelection('flux');

      useAppStore.getState().resetSession();

      const state = useAppStore.getState();
      expect(state.currentSession).toBeNull();
      expect(state.isGenerating).toBe(false);
      expect(state.selectedModels.size).toBe(0);
    });
  });

  describe('selection actions', () => {
    it('toggleModelSelection adds model to selection', () => {
      useAppStore.getState().toggleModelSelection('flux');

      const state = useAppStore.getState();
      expect(state.selectedModels.has('flux')).toBe(true);
      expect(state.isMultiSelectMode).toBe(true);
    });

    it('toggleModelSelection removes model from selection', () => {
      useAppStore.getState().toggleModelSelection('flux');
      useAppStore.getState().toggleModelSelection('flux');

      const state = useAppStore.getState();
      expect(state.selectedModels.has('flux')).toBe(false);
      expect(state.isMultiSelectMode).toBe(false);
    });

    it('selectAllModels selects all 4 models', () => {
      useAppStore.getState().selectAllModels();

      const state = useAppStore.getState();
      expect(state.selectedModels.size).toBe(4);
      expect(state.selectedModels.has('flux')).toBe(true);
      expect(state.selectedModels.has('recraft')).toBe(true);
      expect(state.selectedModels.has('gemini')).toBe(true);
      expect(state.selectedModels.has('openai')).toBe(true);
      expect(state.isMultiSelectMode).toBe(true);
    });

    it('clearSelection clears all selections', () => {
      useAppStore.getState().selectAllModels();
      useAppStore.getState().clearSelection();

      const state = useAppStore.getState();
      expect(state.selectedModels.size).toBe(0);
      expect(state.isMultiSelectMode).toBe(false);
    });
  });

  describe('iteration warning actions', () => {
    it('checkIterationWarning sets warning at 5 iterations', () => {
      const iterations = Array.from({ length: 5 }, (_, i) => createMockIteration(i));
      const session = createMockSession({
        models: {
          ...createMockSession().models,
          flux: createMockModelColumn('flux', { iterations }),
        },
      });
      useAppStore.getState().setCurrentSession(session);

      useAppStore.getState().checkIterationWarning('flux');

      expect(useAppStore.getState().iterationWarnings.flux).toBe(true);
    });

    it('checkIterationWarning does not set warning below 5 iterations', () => {
      const iterations = Array.from({ length: 3 }, (_, i) => createMockIteration(i));
      const session = createMockSession({
        models: {
          ...createMockSession().models,
          flux: createMockModelColumn('flux', { iterations }),
        },
      });
      useAppStore.getState().setCurrentSession(session);

      useAppStore.getState().checkIterationWarning('flux');

      expect(useAppStore.getState().iterationWarnings.flux).toBe(false);
    });

    it('clearIterationWarning clears warning', () => {
      useAppStore.setState((state) => ({
        ...state,
        iterationWarnings: { ...state.iterationWarnings, flux: true },
      }));

      useAppStore.getState().clearIterationWarning('flux');

      expect(useAppStore.getState().iterationWarnings.flux).toBe(false);
    });
  });

  describe('gallery session actions', () => {
    it('setSessions sets session list', () => {
      const sessions = [
        createMockSessionPreview({ sessionId: 'session-1' }),
        createMockSessionPreview({ sessionId: 'session-2' }),
      ];
      useAppStore.getState().setSessions(sessions);

      expect(useAppStore.getState().sessions).toEqual(sessions);
    });

    it('setSelectedGallerySession sets gallery session', () => {
      const session = createMockSession();
      useAppStore.getState().setSelectedGallerySession(session);

      expect(useAppStore.getState().selectedGallerySession).toEqual(session);
    });
  });
});
