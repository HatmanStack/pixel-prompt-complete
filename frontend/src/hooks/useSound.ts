/**
 * useSound Hook
 * Manages sound effects playback with mute toggle and Zustand integration
 */

import { useCallback, useEffect, useRef } from 'react';
import { useUIStore } from '@/stores/useUIStore';
import type { SoundName } from '@/types';

// Sound file paths
const SOUND_FILES: Record<SoundName, string> = {
  click: '/sounds/click.mp3',
  switch: '/sounds/switch.mp3',
  swoosh: '/sounds/swoosh.mp3',
  expand: '/sounds/expand.mp3',
};

interface UseSoundReturn {
  playSound: (soundName: SoundName) => void;
  isMuted: boolean;
  toggleMute: () => void;
  setVolume: (volume: number) => void;
  soundsLoaded: boolean;
}

/**
 * Custom hook for sound effects
 * Integrates with UIStore for global mute state
 */
export function useSound(): UseSoundReturn {
  const { isMuted, volume, soundsLoaded, toggleMute, setVolume, setSoundsLoaded } =
    useUIStore();

  const soundsRef = useRef<Record<SoundName, HTMLAudioElement | null>>({
    click: null,
    switch: null,
    swoosh: null,
    expand: null,
  });

  // Preload all sound files on mount
  useEffect(() => {
    const sounds: Record<SoundName, HTMLAudioElement> = {
      click: new Audio(SOUND_FILES.click),
      switch: new Audio(SOUND_FILES.switch),
      swoosh: new Audio(SOUND_FILES.swoosh),
      expand: new Audio(SOUND_FILES.expand),
    };

    // Set volume and preload for all sounds
    (Object.keys(sounds) as SoundName[]).forEach((key) => {
      const audio = sounds[key];
      audio.volume = volume;
      audio.preload = 'auto';
    });

    soundsRef.current = sounds;
    setSoundsLoaded(true);

    // Sync mute preference from localStorage on mount
    const savedMuted = localStorage.getItem('soundMuted');
    if (savedMuted !== null) {
      const wasMuted = savedMuted === 'true';
      if (wasMuted !== isMuted) {
        toggleMute();
      }
    }

    // Cleanup
    return () => {
      (Object.values(soundsRef.current) as (HTMLAudioElement | null)[]).forEach(
        (audio) => {
          if (audio) {
            audio.pause();
            audio.src = '';
          }
        }
      );
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Update volume when store changes
  useEffect(() => {
    (Object.values(soundsRef.current) as (HTMLAudioElement | null)[]).forEach(
      (audio) => {
        if (audio) {
          audio.volume = volume;
        }
      }
    );
  }, [volume]);

  // Save mute preference to localStorage
  useEffect(() => {
    localStorage.setItem('soundMuted', isMuted.toString());
  }, [isMuted]);

  /**
   * Play a sound effect
   */
  const playSound = useCallback(
    (soundName: SoundName) => {
      if (isMuted || !soundsLoaded) {
        return;
      }

      const audio = soundsRef.current[soundName];
      if (!audio) {
        console.warn(`Sound "${soundName}" not found`);
        return;
      }

      // Stop previous instance and reset to start
      audio.currentTime = 0;
      audio.play().catch((err: Error) => {
        // Handle autoplay restrictions gracefully
        if (err.name !== 'NotAllowedError') {
          console.warn(`Failed to play sound "${soundName}":`, err.message);
        }
      });
    },
    [isMuted, soundsLoaded]
  );

  return {
    playSound,
    isMuted,
    toggleMute,
    setVolume,
    soundsLoaded,
  };
}

export default useSound;
