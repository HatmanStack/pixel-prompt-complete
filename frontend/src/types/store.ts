/**
 * Store State Types
 */

import type { Job, ImageResult, GalleryPreview } from './api';

export type ViewType = 'generation' | 'gallery';

export type SoundName = 'click' | 'swoosh' | 'switch' | 'expand';

export interface AppState {
  // Job state
  currentJob: Job | null;
  isGenerating: boolean;

  // Prompt
  prompt: string;

  // Generated images (array of image results)
  generatedImages: (ImageResult | null)[];

  // Gallery
  selectedGallery: GalleryPreview | null;
  galleries: GalleryPreview[];

  // View
  currentView: ViewType;
}

export interface AppActions {
  // Job actions
  setCurrentJob: (job: Job | null) => void;
  updateJobStatus: (job: Job) => void;
  setIsGenerating: (isGenerating: boolean) => void;

  // Prompt actions
  setPrompt: (prompt: string) => void;

  // Image actions
  setGeneratedImages: (images: (ImageResult | null)[]) => void;
  updateGeneratedImage: (index: number, image: ImageResult) => void;
  resetGeneration: () => void;

  // Gallery actions
  setSelectedGallery: (gallery: GalleryPreview | null) => void;
  setGalleries: (galleries: GalleryPreview[]) => void;

  // View actions
  setCurrentView: (view: ViewType) => void;
}

export interface UIState {
  // Modal state
  isModalOpen: boolean;
  modalContent: string | null;

  // Sound state
  isMuted: boolean;
  volume: number;
  soundsLoaded: boolean;

  // Mobile state
  isGalleryDrawerOpen: boolean;
  isMobileMenuOpen: boolean;
}

export interface UIActions {
  // Modal actions
  openModal: (content: string) => void;
  closeModal: () => void;

  // Sound actions
  toggleMute: () => void;
  setVolume: (volume: number) => void;
  setSoundsLoaded: (loaded: boolean) => void;

  // Mobile actions
  toggleGalleryDrawer: () => void;
  toggleMobileMenu: () => void;
  closeMobileMenu: () => void;
}

export type AppStore = AppState & AppActions;
export type UIStore = UIState & UIActions;
