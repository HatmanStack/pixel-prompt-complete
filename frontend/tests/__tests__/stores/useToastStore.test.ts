/**
 * Tests for useToastStore (Zustand)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useToastStore } from '../../../src/stores/useToastStore';

describe('useToastStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useToastStore.setState({ toasts: [] });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('initial state', () => {
    it('has empty toasts array', () => {
      expect(useToastStore.getState().toasts).toEqual([]);
    });
  });

  describe('showToast', () => {
    it('adds toast with unique id', () => {
      useToastStore.getState().showToast('Test message', 'info', 0);

      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(1);
      expect(toasts[0].message).toBe('Test message');
      expect(toasts[0].type).toBe('info');
      expect(typeof toasts[0].id).toBe('number');
    });

    it('adds multiple toasts with unique ids', () => {
      useToastStore.getState().showToast('Message 1', 'info', 0);
      useToastStore.getState().showToast('Message 2', 'success', 0);

      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(2);
      expect(toasts[0].id).not.toBe(toasts[1].id);
    });

    it('returns toast id', () => {
      const id = useToastStore.getState().showToast('Test', 'info', 0);
      expect(typeof id).toBe('number');
    });
  });

  describe('removeToast', () => {
    it('removes toast by id', () => {
      useToastStore.getState().showToast('Test', 'info', 0);
      const toastId = useToastStore.getState().toasts[0].id;

      useToastStore.getState().removeToast(toastId);

      expect(useToastStore.getState().toasts).toHaveLength(0);
    });

    it('does not remove other toasts', () => {
      useToastStore.getState().showToast('Message 1', 'info', 0);
      useToastStore.getState().showToast('Message 2', 'info', 0);

      const firstId = useToastStore.getState().toasts[0].id;
      useToastStore.getState().removeToast(firstId);

      const toasts = useToastStore.getState().toasts;
      expect(toasts).toHaveLength(1);
      expect(toasts[0].message).toBe('Message 2');
    });
  });

  describe('convenience methods', () => {
    it('success adds success toast', () => {
      useToastStore.getState().success('Success!', 0);

      const toast = useToastStore.getState().toasts[0];
      expect(toast.type).toBe('success');
      expect(toast.message).toBe('Success!');
    });

    it('error adds error toast', () => {
      useToastStore.getState().error('Error!', 0);

      const toast = useToastStore.getState().toasts[0];
      expect(toast.type).toBe('error');
      expect(toast.message).toBe('Error!');
    });

    it('warning adds warning toast', () => {
      useToastStore.getState().warning('Warning!', 0);

      const toast = useToastStore.getState().toasts[0];
      expect(toast.type).toBe('warning');
      expect(toast.message).toBe('Warning!');
    });

    it('info adds info toast', () => {
      useToastStore.getState().info('Info!', 0);

      const toast = useToastStore.getState().toasts[0];
      expect(toast.type).toBe('info');
      expect(toast.message).toBe('Info!');
    });
  });

  describe('auto-dismiss', () => {
    it('auto-removes toast after duration', () => {
      useToastStore.getState().showToast('Auto dismiss', 'info', 3000);

      expect(useToastStore.getState().toasts).toHaveLength(1);

      vi.advanceTimersByTime(3000);

      expect(useToastStore.getState().toasts).toHaveLength(0);
    });

    it('does not auto-remove when duration is 0', () => {
      useToastStore.getState().showToast('No auto dismiss', 'info', 0);

      vi.advanceTimersByTime(10000);

      expect(useToastStore.getState().toasts).toHaveLength(1);
    });
  });

  describe('store methods', () => {
    it('returns all expected methods', () => {
      const state = useToastStore.getState();

      expect(state.toasts).toBeDefined();
      expect(typeof state.showToast).toBe('function');
      expect(typeof state.removeToast).toBe('function');
      expect(typeof state.success).toBe('function');
      expect(typeof state.error).toBe('function');
      expect(typeof state.warning).toBe('function');
      expect(typeof state.info).toBe('function');
    });
  });
});
