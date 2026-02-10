/**
 * Store State Types
 */

import type { Session, SessionPreview, ModelName, Iteration } from './api';

export type ViewType = 'generation' | 'gallery';

export type SoundName = 'click' | 'swoosh' | 'switch' | 'expand';

export interface AppState {
  currentSession: Session | null;
  isGenerating: boolean;
  prompt: string;

  selectedModels: Set<ModelName>;
  isMultiSelectMode: boolean;

  sessions: SessionPreview[];
  selectedGallerySession: Session | null;

  iterationWarnings: Record<ModelName, boolean>;

  currentView: ViewType;
}

export interface AppActions {
  setPrompt: (prompt: string) => void;

  setCurrentSession: (session: Session | null) => void;
  updateModelIteration: (model: ModelName, iteration: Iteration) => void;
  setIsGenerating: (isGenerating: boolean) => void;
  resetSession: () => void;

  toggleModelSelection: (model: ModelName) => void;
  selectAllModels: () => void;
  clearSelection: () => void;
  setMultiSelectMode: (enabled: boolean) => void;

  setSessions: (sessions: SessionPreview[]) => void;
  setSelectedGallerySession: (session: Session | null) => void;

  checkIterationWarning: (model: ModelName) => void;
  clearIterationWarning: (model: ModelName) => void;

  resetGeneration: () => void;
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
