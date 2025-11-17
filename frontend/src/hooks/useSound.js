/**
 * useSound Hook
 * Manages sound effects playback with mute toggle and localStorage persistence
 */

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook for sound effects
 * @returns {Object} Sound playback functions and mute state
 */
function useSound() {
  const [isMuted, setIsMuted] = useState(() => {
    // Load mute preference from localStorage
    const saved = localStorage.getItem('soundMuted');
    return saved === 'true';
  });

  const [soundsLoaded, setSoundsLoaded] = useState(false);
  const soundsRef = useRef({});

  // Preload all sound files on mount
  useEffect(() => {
    const sounds = {
      click: new Audio('/sounds/click.mp3'),
      switch: new Audio('/sounds/switch.mp3'),
      swoosh: new Audio('/sounds/swoosh.mp3'),
      expand: new Audio('/sounds/expand.mp3'),
    };

    // Set volume for all sounds (50% by default)
    Object.values(sounds).forEach((audio) => {
      audio.volume = 0.5;
      // Preload the audio
      audio.preload = 'auto';
    });

    soundsRef.current = sounds;
    setSoundsLoaded(true);

    console.log('Sound effects preloaded');

    // Cleanup
    return () => {
      Object.values(sounds).forEach((audio) => {
        audio.pause();
        audio.src = '';
      });
    };
  }, []);

  // Save mute preference to localStorage
  useEffect(() => {
    localStorage.setItem('soundMuted', isMuted.toString());
  }, [isMuted]);

  /**
   * Play a sound effect
   * @param {string} soundName - Name of the sound to play (click, switch, swoosh, expand)
   */
  const playSound = useCallback(
    (soundName) => {
      if (isMuted || !soundsLoaded) {
        return;
      }

      const audio = soundsRef.current[soundName];
      if (!audio) {
        console.warn(`Sound "${soundName}" not found`);
        return;
      }

      // Reset to start and play
      audio.currentTime = 0;
      audio.play().catch((err) => {
        // Handle autoplay restrictions gracefully
        if (err.name === 'NotAllowedError') {
          console.log('Sound autoplay blocked by browser. User interaction required.');
        } else {
          console.warn(`Failed to play sound "${soundName}":`, err.message);
        }
      });
    },
    [isMuted, soundsLoaded]
  );

  /**
   * Toggle mute state
   */
  const toggleMute = useCallback(() => {
    setIsMuted((prev) => !prev);
  }, []);

  /**
   * Set volume for all sounds
   * @param {number} volume - Volume level (0-1)
   */
  const setVolume = useCallback((volume) => {
    const clampedVolume = Math.max(0, Math.min(1, volume));
    Object.values(soundsRef.current).forEach((audio) => {
      audio.volume = clampedVolume;
    });
  }, []);

  return {
    playSound,
    isMuted,
    toggleMute,
    setVolume,
    soundsLoaded,
  };
}

export default useSound;
