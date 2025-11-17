/**
 * AppContext
 * Global state management using React Context
 */

import { createContext, useContext, useState } from 'react';
import useSound from '../hooks/useSound';

// Create context
const AppContext = createContext(null);

/**
 * AppProvider Component
 * Wraps the application and provides global state
 */
export function AppProvider({ children }) {
  // Current job state
  const [currentJob, setCurrentJob] = useState(null);

  // Prompt and parameters
  const [prompt, setPrompt] = useState('');
  const [parameters, setParameters] = useState({
    steps: 28,
    guidance: 5,
    control: 1.0,
  });

  // Generated images (array of 9 image objects)
  const [generatedImages, setGeneratedImages] = useState(Array(9).fill(null));

  // Gallery state
  const [selectedGallery, setSelectedGallery] = useState(null);

  // UI state
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentView, setCurrentView] = useState('generation'); // 'generation' | 'gallery'

  // Sound effects
  const { playSound, isMuted, toggleMute, setVolume, soundsLoaded } = useSound();

  // Helper functions
  const updateJobStatus = (jobStatus) => {
    setCurrentJob(jobStatus);
  };

  const resetGeneration = () => {
    setCurrentJob(null);
    setGeneratedImages(Array(9).fill(null));
    setIsGenerating(false);
  };

  const updateParameter = (key, value) => {
    setParameters(prev => ({
      ...prev,
      [key]: value,
    }));
  };

  const updateGeneratedImage = (index, imageData) => {
    setGeneratedImages(prev => {
      const newImages = [...prev];
      newImages[index] = imageData;
      return newImages;
    });
  };

  // Context value
  const value = {
    // Job state
    currentJob,
    setCurrentJob,
    updateJobStatus,

    // Prompt and parameters
    prompt,
    setPrompt,
    parameters,
    setParameters,
    updateParameter,

    // Generated images
    generatedImages,
    setGeneratedImages,
    updateGeneratedImage,

    // Gallery
    selectedGallery,
    setSelectedGallery,

    // UI state
    isGenerating,
    setIsGenerating,
    currentView,
    setCurrentView,

    // Sound effects
    playSound,
    isMuted,
    toggleMute,
    setVolume,
    soundsLoaded,

    // Helper functions
    resetGeneration,
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}

/**
 * useApp Hook
 * Custom hook to access app context
 * @returns {Object} App context value
 */
export function useApp() {
  const context = useContext(AppContext);

  if (!context) {
    throw new Error('useApp must be used within AppProvider');
  }

  return context;
}

export default AppContext;
