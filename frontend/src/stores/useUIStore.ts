/**
 * UI Store
 * UI-specific state using Zustand
 */

import { create } from 'zustand';
import type { UIStore } from '@/types';

export const useUIStore = create<UIStore>((set) => ({
  // Initial state
  isModalOpen: false,
  modalContent: null,
  isCompareOpen: false,
  isMuted: false,
  volume: 0.5,
  soundsLoaded: false,
  isGalleryDrawerOpen: false,
  isMobileMenuOpen: false,
  focusedModel: null,

  // Modal actions
  openModal: (content: string) => set({ isModalOpen: true, modalContent: content }),

  closeModal: () => set({ isModalOpen: false, modalContent: null }),

  // Compare modal actions
  openCompare: () => set({ isCompareOpen: true }),
  closeCompare: () => set({ isCompareOpen: false }),

  // Sound actions
  toggleMute: () => set((state) => ({ isMuted: !state.isMuted })),

  setVolume: (volume: number) => set({ volume: Math.max(0, Math.min(1, volume)) }),

  setSoundsLoaded: (loaded: boolean) => set({ soundsLoaded: loaded }),

  // Mobile actions
  toggleGalleryDrawer: () => set((state) => ({ isGalleryDrawerOpen: !state.isGalleryDrawerOpen })),

  toggleMobileMenu: () => set((state) => ({ isMobileMenuOpen: !state.isMobileMenuOpen })),

  closeMobileMenu: () => set({ isMobileMenuOpen: false }),

  // Column focus actions (desktop only)
  setFocusedModel: (model) => set({ focusedModel: model }),
  toggleFocus: (model) =>
    set((state) => ({
      focusedModel: state.focusedModel === model ? null : model,
    })),
}));
