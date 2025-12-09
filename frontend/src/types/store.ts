/**
 * Store State Types
 */

import type {
  Job,
  ImageResult,
  GalleryPreview,
  Session,
  SessionPreview,
  ModelName,
  Iteration,
} from './api';

export type ViewType = 'generation' | 'gallery';

export type SoundName = 'click' | 'swoosh' | 'switch' | 'expand';

// ====================
// New Session-based App State
// ====================

export interface AppState {
  // Session state (new)
  currentSession: Session | null;
  isGenerating: boolean;
  prompt: string;

  // Selection state (new)
  selectedModels: Set<ModelName>;
  isMultiSelectMode: boolean;

  // Gallery state (new)
  sessions: SessionPreview[];
  selectedGallerySession: Session | null;

  // UI state (new)
  iterationWarnings: Record<ModelName, boolean>;

  // Legacy state (for backwards compatibility during transition)
  currentJob: Job | null;
  generatedImages: (ImageResult | null)[];
  selectedGallery: GalleryPreview | null;
  galleries: GalleryPreview[];
  currentView: ViewType;
}

export interface AppActions {
  // Prompt
  setPrompt: (prompt: string) => void;

  // Session actions (new)
  setCurrentSession: (session: Session | null) => void;
  updateModelIteration: (model: ModelName, iteration: Iteration) => void;
  setIsGenerating: (isGenerating: boolean) => void;
  resetSession: () => void;

  // Selection actions (new)
  toggleModelSelection: (model: ModelName) => void;
  selectAllModels: () => void;
  clearSelection: () => void;
  setMultiSelectMode: (enabled: boolean) => void;

  // Gallery actions (new)
  setSessions: (sessions: SessionPreview[]) => void;
  setSelectedGallerySession: (session: Session | null) => void;

  // Warnings (new)
  checkIterationWarning: (model: ModelName) => void;
  clearIterationWarning: (model: ModelName) => void;

  // Legacy actions (for backwards compatibility)
  setCurrentJob: (job: Job | null) => void;
  updateJobStatus: (job: Job) => void;
  setGeneratedImages: (images: (ImageResult | null)[]) => void;
  updateGeneratedImage: (index: number, image: ImageResult) => void;
  resetGeneration: () => void;
  setSelectedGallery: (gallery: GalleryPreview | null) => void;
  setGalleries: (galleries: GalleryPreview[]) => void;
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
