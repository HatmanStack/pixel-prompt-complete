/**
 * Tests for useUIStore (Zustand)
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore } from '../../../src/stores/useUIStore';

describe('useUIStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useUIStore.setState({
      isModalOpen: false,
      modalContent: null,
      isMuted: false,
      volume: 0.5,
      soundsLoaded: false,
      isGalleryDrawerOpen: false,
      isMobileMenuOpen: false,
    });
  });

  describe('initial state', () => {
    it('has correct initial values', () => {
      const state = useUIStore.getState();

      expect(state.isModalOpen).toBe(false);
      expect(state.modalContent).toBeNull();
      expect(state.isMuted).toBe(false);
      expect(state.volume).toBe(0.5);
      expect(state.soundsLoaded).toBe(false);
      expect(state.isGalleryDrawerOpen).toBe(false);
      expect(state.isMobileMenuOpen).toBe(false);
    });
  });

  describe('modal actions', () => {
    it('openModal opens modal with content', () => {
      useUIStore.getState().openModal('test-content');

      const state = useUIStore.getState();
      expect(state.isModalOpen).toBe(true);
      expect(state.modalContent).toBe('test-content');
    });

    it('closeModal closes modal and clears content', () => {
      useUIStore.getState().openModal('test-content');
      useUIStore.getState().closeModal();

      const state = useUIStore.getState();
      expect(state.isModalOpen).toBe(false);
      expect(state.modalContent).toBeNull();
    });
  });

  describe('sound actions', () => {
    it('toggleMute toggles mute state', () => {
      expect(useUIStore.getState().isMuted).toBe(false);

      useUIStore.getState().toggleMute();
      expect(useUIStore.getState().isMuted).toBe(true);

      useUIStore.getState().toggleMute();
      expect(useUIStore.getState().isMuted).toBe(false);
    });

    it('setVolume sets volume within bounds', () => {
      useUIStore.getState().setVolume(0.8);
      expect(useUIStore.getState().volume).toBe(0.8);
    });

    it('setVolume clamps to minimum 0', () => {
      useUIStore.getState().setVolume(-0.5);
      expect(useUIStore.getState().volume).toBe(0);
    });

    it('setVolume clamps to maximum 1', () => {
      useUIStore.getState().setVolume(1.5);
      expect(useUIStore.getState().volume).toBe(1);
    });

    it('setSoundsLoaded sets loaded state', () => {
      useUIStore.getState().setSoundsLoaded(true);
      expect(useUIStore.getState().soundsLoaded).toBe(true);

      useUIStore.getState().setSoundsLoaded(false);
      expect(useUIStore.getState().soundsLoaded).toBe(false);
    });
  });

  describe('mobile actions', () => {
    it('toggleGalleryDrawer toggles drawer state', () => {
      expect(useUIStore.getState().isGalleryDrawerOpen).toBe(false);

      useUIStore.getState().toggleGalleryDrawer();
      expect(useUIStore.getState().isGalleryDrawerOpen).toBe(true);

      useUIStore.getState().toggleGalleryDrawer();
      expect(useUIStore.getState().isGalleryDrawerOpen).toBe(false);
    });

    it('toggleMobileMenu toggles menu state', () => {
      expect(useUIStore.getState().isMobileMenuOpen).toBe(false);

      useUIStore.getState().toggleMobileMenu();
      expect(useUIStore.getState().isMobileMenuOpen).toBe(true);

      useUIStore.getState().toggleMobileMenu();
      expect(useUIStore.getState().isMobileMenuOpen).toBe(false);
    });

    it('closeMobileMenu closes menu', () => {
      useUIStore.getState().toggleMobileMenu();
      expect(useUIStore.getState().isMobileMenuOpen).toBe(true);

      useUIStore.getState().closeMobileMenu();
      expect(useUIStore.getState().isMobileMenuOpen).toBe(false);
    });
  });
});
