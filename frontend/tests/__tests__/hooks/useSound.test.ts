/**
 * Tests for useSound hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSound } from '../../../src/hooks/useSound';
import { useUIStore } from '../../../src/stores/useUIStore';

// Mock HTMLAudioElement
class MockAudio {
  volume = 0.5;
  currentTime = 0;
  preload = '';
  src = '';

  play = vi.fn().mockResolvedValue(undefined);
  pause = vi.fn();
  load = vi.fn();
}

describe('useSound', () => {
  beforeEach(() => {
    // Reset store state
    useUIStore.setState({
      isMuted: false,
      volume: 0.5,
      soundsLoaded: false,
    });

    // Mock Audio constructor
    vi.stubGlobal('Audio', vi.fn().mockImplementation(() => new MockAudio()));

    // Mock localStorage
    const localStorageMock = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    vi.stubGlobal('localStorage', localStorageMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('preloads sounds on mount', () => {
    renderHook(() => useSound());

    // Audio constructor should be called for each sound
    expect(Audio).toHaveBeenCalledTimes(4);
    expect(Audio).toHaveBeenCalledWith('/sounds/click.wav');
    expect(Audio).toHaveBeenCalledWith('/sounds/switch.wav');
    expect(Audio).toHaveBeenCalledWith('/sounds/swoosh.mp3');
    expect(Audio).toHaveBeenCalledWith('/sounds/expand.wav');
  });

  it('sets soundsLoaded to true after initialization', () => {
    renderHook(() => useSound());

    expect(useUIStore.getState().soundsLoaded).toBe(true);
  });

  it('returns muted state from store', () => {
    useUIStore.setState({ isMuted: true });
    const { result } = renderHook(() => useSound());

    expect(result.current.isMuted).toBe(true);
  });

  it('toggleMute updates store state', () => {
    const { result } = renderHook(() => useSound());

    expect(result.current.isMuted).toBe(false);

    act(() => {
      result.current.toggleMute();
    });

    expect(result.current.isMuted).toBe(true);
  });

  it('saves mute preference to localStorage', () => {
    const { result } = renderHook(() => useSound());

    act(() => {
      result.current.toggleMute();
    });

    expect(localStorage.setItem).toHaveBeenCalledWith('soundMuted', 'true');
  });

  it('does not play sound when muted', () => {
    useUIStore.setState({ isMuted: true, soundsLoaded: true });
    const { result } = renderHook(() => useSound());

    act(() => {
      result.current.playSound('click');
    });

    // Play should not be called when muted
    const mockAudioInstance = (Audio as ReturnType<typeof vi.fn>).mock
      .results[0].value;
    expect(mockAudioInstance.play).not.toHaveBeenCalled();
  });

  it('plays sound when sounds are loaded and not muted', () => {
    useUIStore.setState({ isMuted: false, soundsLoaded: false });
    const { result } = renderHook(() => useSound());

    // After mounting, sounds should be loaded
    expect(result.current.soundsLoaded).toBe(true);

    // Get the first mock audio instance (click)
    const mockAudioInstance = (Audio as ReturnType<typeof vi.fn>).mock
      .results[0].value;

    act(() => {
      result.current.playSound('click');
    });

    // Play should be called when not muted and sounds loaded
    expect(mockAudioInstance.play).toHaveBeenCalled();
  });

  it('setVolume updates volume in store', () => {
    const { result } = renderHook(() => useSound());

    act(() => {
      result.current.setVolume(0.8);
    });

    expect(useUIStore.getState().volume).toBe(0.8);
  });

  it('clamps volume between 0 and 1', () => {
    const { result } = renderHook(() => useSound());

    act(() => {
      result.current.setVolume(1.5);
    });
    expect(useUIStore.getState().volume).toBe(1);

    act(() => {
      result.current.setVolume(-0.5);
    });
    expect(useUIStore.getState().volume).toBe(0);
  });
});
