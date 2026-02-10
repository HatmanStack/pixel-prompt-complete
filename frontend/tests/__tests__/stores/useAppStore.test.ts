/**
 * Tests for useAppStore (Zustand) - current session-based state
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '../../../src/stores/useAppStore';

describe('useAppStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useAppStore.setState({
      isGenerating: false,
      prompt: '',
      currentView: 'generation',
    });
  });

  describe('initial state', () => {
    it('has correct initial values', () => {
      const state = useAppStore.getState();

      expect(state.isGenerating).toBe(false);
      expect(state.prompt).toBe('');
      expect(state.currentView).toBe('generation');
    });
  });

  describe('prompt actions', () => {
    it('setPrompt sets prompt text', () => {
      useAppStore.getState().setPrompt('A beautiful sunset');

      expect(useAppStore.getState().prompt).toBe('A beautiful sunset');
    });

    it('setPrompt can clear prompt', () => {
      useAppStore.getState().setPrompt('Some text');
      useAppStore.getState().setPrompt('');

      expect(useAppStore.getState().prompt).toBe('');
    });
  });

  describe('generating actions', () => {
    it('setIsGenerating sets generating flag', () => {
      useAppStore.getState().setIsGenerating(true);
      expect(useAppStore.getState().isGenerating).toBe(true);

      useAppStore.getState().setIsGenerating(false);
      expect(useAppStore.getState().isGenerating).toBe(false);
    });

    it('resetGeneration clears session state and generating flag', () => {
      useAppStore.getState().setIsGenerating(true);

      useAppStore.getState().resetGeneration();

      const state = useAppStore.getState();
      expect(state.currentSession).toBeNull();
      expect(state.isGenerating).toBe(false);
    });
  });

  describe('view actions', () => {
    it('setCurrentView changes view', () => {
      useAppStore.getState().setCurrentView('gallery');
      expect(useAppStore.getState().currentView).toBe('gallery');

      useAppStore.getState().setCurrentView('generation');
      expect(useAppStore.getState().currentView).toBe('generation');
    });
  });
});
