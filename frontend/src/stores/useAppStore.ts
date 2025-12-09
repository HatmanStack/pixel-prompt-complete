/**
 * App Store
 * Main application state using Zustand
 * Supports both new session-based state and legacy job-based state
 */

import { create } from 'zustand';
import type { AppStore, ViewType } from '@/types';
import type {
  Job,
  ImageResult,
  GalleryPreview,
  Session,
  SessionPreview,
  ModelName,
  Iteration,
} from '@/types';
import { MODELS } from '@/types';

const INITIAL_IMAGES: (ImageResult | null)[] = Array(9).fill(null);

const INITIAL_ITERATION_WARNINGS: Record<ModelName, boolean> = {
  flux: false,
  recraft: false,
  gemini: false,
  openai: false,
};

export const useAppStore = create<AppStore>((set) => ({
  // ====================
  // New Session-based State
  // ====================
  currentSession: null,
  isGenerating: false,
  prompt: '',

  // Selection state
  selectedModels: new Set<ModelName>(),
  isMultiSelectMode: false,

  // Gallery state (new)
  sessions: [],
  selectedGallerySession: null,

  // Iteration warnings
  iterationWarnings: INITIAL_ITERATION_WARNINGS,

  // ====================
  // Legacy State
  // ====================
  currentJob: null,
  generatedImages: INITIAL_IMAGES,
  selectedGallery: null,
  galleries: [],
  currentView: 'generation' as ViewType,

  // ====================
  // Prompt Actions
  // ====================
  setPrompt: (prompt: string) => set({ prompt }),

  // ====================
  // New Session Actions
  // ====================
  setCurrentSession: (session: Session | null) => set({ currentSession: session }),

  updateModelIteration: (model: ModelName, iteration: Iteration) =>
    set((state) => {
      if (!state.currentSession) return state;

      const updatedModels = { ...state.currentSession.models };
      const column = updatedModels[model];

      if (!column) return state;

      // Find existing iteration or add new one
      const existingIndex = column.iterations.findIndex(
        (it) => it.index === iteration.index
      );

      if (existingIndex >= 0) {
        column.iterations[existingIndex] = iteration;
      } else {
        column.iterations = [...column.iterations, iteration];
      }

      return {
        currentSession: {
          ...state.currentSession,
          models: updatedModels,
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

  // ====================
  // Selection Actions
  // ====================
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

  // ====================
  // Gallery Actions (New)
  // ====================
  setSessions: (sessions: SessionPreview[]) => set({ sessions }),

  setSelectedGallerySession: (session: Session | null) =>
    set({ selectedGallerySession: session }),

  // ====================
  // Iteration Warning Actions
  // ====================
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

  // ====================
  // Legacy Job Actions
  // ====================
  setCurrentJob: (job: Job | null) => set({ currentJob: job }),

  updateJobStatus: (job: Job) => set({ currentJob: job }),

  setGeneratedImages: (images: (ImageResult | null)[]) =>
    set({ generatedImages: images }),

  updateGeneratedImage: (index: number, image: ImageResult) =>
    set((state) => {
      const newImages = [...state.generatedImages];
      newImages[index] = image;
      return { generatedImages: newImages };
    }),

  resetGeneration: () =>
    set({
      currentJob: null,
      generatedImages: INITIAL_IMAGES,
      isGenerating: false,
      // Also reset new session state
      currentSession: null,
      selectedModels: new Set<ModelName>(),
      iterationWarnings: INITIAL_ITERATION_WARNINGS,
    }),

  // ====================
  // Legacy Gallery Actions
  // ====================
  setSelectedGallery: (gallery: GalleryPreview | null) =>
    set({ selectedGallery: gallery }),

  setGalleries: (galleries: GalleryPreview[]) => set({ galleries }),

  // ====================
  // View Actions
  // ====================
  setCurrentView: (view: ViewType) => set({ currentView: view }),
}));
