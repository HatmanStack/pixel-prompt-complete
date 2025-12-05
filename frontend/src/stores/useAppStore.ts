/**
 * App Store
 * Main application state using Zustand
 */

import { create } from 'zustand';
import type { AppStore, ViewType } from '@/types';
import type { Job, ImageResult, GalleryPreview } from '@/types';

const INITIAL_IMAGES: (ImageResult | null)[] = Array(9).fill(null);

export const useAppStore = create<AppStore>((set) => ({
  // Initial state
  currentJob: null,
  isGenerating: false,
  prompt: '',
  generatedImages: INITIAL_IMAGES,
  selectedGallery: null,
  galleries: [],
  currentView: 'generation' as ViewType,

  // Job actions
  setCurrentJob: (job: Job | null) => set({ currentJob: job }),

  updateJobStatus: (job: Job) => set({ currentJob: job }),

  setIsGenerating: (isGenerating: boolean) => set({ isGenerating }),

  // Prompt actions
  setPrompt: (prompt: string) => set({ prompt }),

  // Image actions
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
    }),

  // Gallery actions
  setSelectedGallery: (gallery: GalleryPreview | null) =>
    set({ selectedGallery: gallery }),

  setGalleries: (galleries: GalleryPreview[]) => set({ galleries }),

  // View actions
  setCurrentView: (view: ViewType) => set({ currentView: view }),
}));
