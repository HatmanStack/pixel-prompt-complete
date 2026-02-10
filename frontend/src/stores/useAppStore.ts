/**
 * App Store
 * Main application state using Zustand
 */

import { create } from 'zustand';
import type { AppStore, ViewType } from '@/types';
import type { Session, SessionPreview, ModelName, Iteration } from '@/types';
import { MODELS } from '@/types';

const INITIAL_ITERATION_WARNINGS: Record<ModelName, boolean> = {
  flux: false,
  recraft: false,
  gemini: false,
  openai: false,
};

export const useAppStore = create<AppStore>((set) => ({
  // Session state
  currentSession: null,
  isGenerating: false,
  prompt: '',

  // Selection state
  selectedModels: new Set<ModelName>(),
  isMultiSelectMode: false,

  // Gallery state
  sessions: [],
  selectedGallerySession: null,

  // Iteration warnings
  iterationWarnings: INITIAL_ITERATION_WARNINGS,

  // View
  currentView: 'generation' as ViewType,

  // Prompt Actions
  setPrompt: (prompt: string) => set({ prompt }),

  // Session Actions
  setCurrentSession: (session: Session | null) => set({ currentSession: session }),

  updateModelIteration: (model: ModelName, iteration: Iteration) =>
    set((state) => {
      if (!state.currentSession) return state;

      const column = state.currentSession.models[model];
      if (!column) return state;

      const existingIndex = column.iterations.findIndex((it) => it.index === iteration.index);

      const newIterations =
        existingIndex >= 0
          ? column.iterations.map((it, i) => (i === existingIndex ? iteration : it))
          : [...column.iterations, iteration];

      return {
        currentSession: {
          ...state.currentSession,
          models: {
            ...state.currentSession.models,
            [model]: {
              ...column,
              iterations: newIterations,
            },
          },
        },
      };
    }),

  setIsGenerating: (isGenerating: boolean) => set({ isGenerating }),

  resetSession: () =>
    set({
      currentSession: null,
      isGenerating: false,
      selectedModels: new Set<ModelName>(),
      iterationWarnings: INITIAL_ITERATION_WARNINGS,
    }),

  // Selection Actions
  toggleModelSelection: (model: ModelName) =>
    set((state) => {
      const newSelection = new Set(state.selectedModels);
      if (newSelection.has(model)) {
        newSelection.delete(model);
      } else {
        newSelection.add(model);
      }
      return {
        selectedModels: newSelection,
        isMultiSelectMode: newSelection.size > 0,
      };
    }),

  selectAllModels: () =>
    set({
      selectedModels: new Set(MODELS),
      isMultiSelectMode: true,
    }),

  clearSelection: () =>
    set({
      selectedModels: new Set<ModelName>(),
      isMultiSelectMode: false,
    }),

  setMultiSelectMode: (enabled: boolean) =>
    set((state) => ({
      isMultiSelectMode: enabled,
      selectedModels: enabled ? state.selectedModels : new Set<ModelName>(),
    })),

  // Gallery Actions
  setSessions: (sessions: SessionPreview[]) => set({ sessions }),

  setSelectedGallerySession: (session: Session | null) => set({ selectedGallerySession: session }),

  // Iteration Warning Actions
  checkIterationWarning: (model: ModelName) =>
    set((state) => {
      const column = state.currentSession?.models[model];
      if (column && column.iterations.length >= 5) {
        return {
          iterationWarnings: {
            ...state.iterationWarnings,
            [model]: true,
          },
        };
      }
      return state;
    }),

  clearIterationWarning: (model: ModelName) =>
    set((state) => ({
      iterationWarnings: {
        ...state.iterationWarnings,
        [model]: false,
      },
    })),

  // Reset
  resetGeneration: () =>
    set({
      currentSession: null,
      isGenerating: false,
      selectedModels: new Set<ModelName>(),
      iterationWarnings: INITIAL_ITERATION_WARNINGS,
    }),

  // View Actions
  setCurrentView: (view: ViewType) => set({ currentView: view }),
}));
