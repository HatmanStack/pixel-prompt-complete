/**
 * GenerationPanel Component
 * Main panel that integrates all generation components
 */

import { useEffect, useState } from 'react';
import { useApp } from '../../context/AppContext';
import useJobPolling from '../../hooks/useJobPolling';
import useImageLoader from '../../hooks/useImageLoader';
import { generateImages } from '../../api/client';
import PromptInput from './PromptInput';
import RandomPromptButton from '../features/generation/RandomPromptButton';
import PromptEnhancer from './PromptEnhancer';
import GenerateButton from './GenerateButton';
import ImageGrid from './ImageGrid';
import GalleryBrowser from '../gallery/GalleryBrowser';
import styles from './GenerationPanel.module.css';

function GenerationPanel() {
  const {
    prompt,
    setPrompt,
    currentJob,
    setCurrentJob,
    generatedImages,
    setGeneratedImages,
    isGenerating,
    setIsGenerating,
    resetGeneration,
  } = useApp();

  const [errorMessage, setErrorMessage] = useState(null);
  const [modelNames, setModelNames] = useState([]);
  const [viewingGallery, setViewingGallery] = useState(false);

  // Poll job status when we have a job ID
  const { jobStatus, error: pollingError } = useJobPolling(
    currentJob?.jobId,
    2000
  );

  // Load images from S3 (fetches JSON and converts base64 to blob URLs)
  const { images: loadedImages } = useImageLoader(jobStatus);

  // Update generated images when job status changes
  useEffect(() => {
    if (jobStatus) {
      setCurrentJob(jobStatus);

      // Extract model names (update on each job)
      if (jobStatus.results) {
        const names = jobStatus.results.map(r => r.model || 'Unknown');
        setModelNames(names);
      }

      // Update image states based on results and loaded images
      if (jobStatus.results) {
        const updatedImages = jobStatus.results.map((result, index) => ({
          model: result.model,
          status: result.status,
          imageUrl: result.imageUrl,
          image: loadedImages[index], // Use loaded blob URL from hook
          error: result.error,
          completedAt: result.completedAt,
        }));

        console.log('[GENERATION_PANEL] Updating generatedImages:', updatedImages.map((img, i) => ({
          index: i,
          model: img.model,
          status: img.status,
          hasImage: !!img.image,
          imagePreview: img.image ? img.image.substring(0, 50) : null
        })));

        setGeneratedImages(updatedImages);
      }

      // Check if job is complete
      if (jobStatus.status === 'completed' || jobStatus.status === 'partial') {
        setIsGenerating(false);
      } else if (jobStatus.status === 'failed') {
        setIsGenerating(false);
        setErrorMessage('Generation failed. Please try again.');
      }
    }
  }, [jobStatus, loadedImages]);

  // Handle polling errors
  useEffect(() => {
    if (pollingError) {
      setIsGenerating(false);
      setErrorMessage(pollingError);
    }
  }, [pollingError]);

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setErrorMessage('Please enter a prompt');
      return;
    }

    try {
      // Reset previous generation
      resetGeneration();
      setErrorMessage(null);
      setIsGenerating(true);

      // Call API to start generation
      const response = await generateImages(prompt);

      if (response.jobId) {
        setCurrentJob({
          jobId: response.jobId,
          status: 'in_progress',
        });
      } else {
        throw new Error('No job ID received');
      }
    } catch (error) {
      console.error('Generation error:', error);
      setIsGenerating(false);

      // Handle specific error codes
      if (error.status === 429) {
        setErrorMessage('Rate limit exceeded. Please try again later.');
      } else if (error.status === 400 && error.message?.includes('filter')) {
        setErrorMessage('Prompt contains inappropriate content. Please try a different prompt.');
      } else {
        setErrorMessage(error.message || 'Failed to start generation. Please try again.');
      }
    }
  };

  // Listen for keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't trigger shortcuts when typing in inputs
      const isTyping = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);

      // Ctrl+Enter to generate
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !isTyping) {
        if (!isGenerating && prompt.trim()) {
          handleGenerate();
        }
      }

      // Ctrl+R for random prompt
      if ((e.ctrlKey || e.metaKey) && e.key === 'r' && !isTyping) {
        e.preventDefault(); // Prevent browser reload
        if (!isGenerating) {
          // Trigger via event for RandomPromptButton to handle
          const event = new CustomEvent('random-prompt-trigger');
          document.dispatchEvent(event);
        }
      }

      // Ctrl+E for enhance prompt
      if ((e.ctrlKey || e.metaKey) && e.key === 'e' && !isTyping) {
        e.preventDefault();
        if (!isGenerating && prompt.trim()) {
          // Trigger via event for PromptEnhancer to handle
          const event = new CustomEvent('enhance-prompt-trigger');
          document.dispatchEvent(event);
        }
      }

      // Ctrl+Shift+D for download all images
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D' && !isTyping) {
        e.preventDefault();
        // Trigger via event for ImageGrid to handle
        const event = new CustomEvent('download-all-trigger');
        document.dispatchEvent(event);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [prompt, isGenerating]);

  const getProgressText = () => {
    if (!jobStatus || !jobStatus.results) return '';

    const completed = jobStatus.results.filter(r => r.status === 'completed').length;
    const total = jobStatus.results.length;

    if (completed === total) {
      return 'All images generated!';
    }

    return `Generating: ${completed} / ${total} models complete`;
  };

  // Handle gallery selection - populate grid with gallery images
  const handleGallerySelect = (gallery) => {
    if (!gallery) {
      setViewingGallery(false);
      return;
    }

    setViewingGallery(true);

    // Convert gallery images to generatedImages format
    const galleryImages = gallery.images.map((img, index) => ({
      model: img.model,
      status: 'completed',
      imageUrl: img.url,
      image: img.blobUrl || img.url,  // Use blob URL if available
      error: null,
      completedAt: img.timestamp,
    }));

    setGeneratedImages(galleryImages);
    setModelNames(gallery.images.map(img => img.model || `Model ${index + 1}`));
  };

  return (
    <div className={styles.panel}>
      {/* Input Section */}
      <div className={styles.inputSection}>
        <PromptInput
          value={prompt}
          onChange={setPrompt}
          onClear={() => setPrompt('')}
          disabled={isGenerating}
        />

        <div className={styles.promptActions}>
          <RandomPromptButton
            onSelectPrompt={setPrompt}
            disabled={isGenerating}
          />
          <PromptEnhancer
            currentPrompt={prompt}
            onUsePrompt={setPrompt}
            disabled={isGenerating}
          />
        </div>

        <GenerateButton
          onClick={handleGenerate}
          isGenerating={isGenerating}
          disabled={!prompt.trim() || isGenerating}
        />

        {/* Error Message */}
        {errorMessage && (
          <div className={styles.error} role="alert">
            <span className={styles.errorIcon}>⚠</span>
            <span>{errorMessage}</span>
            <button
              className={styles.dismissButton}
              onClick={() => setErrorMessage(null)}
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}

        {/* Progress */}
        {isGenerating && (
          <div className={styles.progress} aria-live="polite">
            <div className={styles.progressBar}>
              <div
                className={styles.progressFill}
                style={{
                  width: `${jobStatus?.results ? (jobStatus.results.filter(r => r.status === 'completed').length / jobStatus.results.length) * 100 : 0}%`
                }}
              />
            </div>
            <p className={styles.progressText}>{getProgressText()}</p>
          </div>
        )}
      </div>

      {/* Gallery Section */}
      <div className={styles.gallerySection}>
        <GalleryBrowser onGallerySelect={handleGallerySelect} />
      </div>

      {/* Results Section */}
      <div className={styles.resultsSection}>
        <ImageGrid images={generatedImages} modelNames={modelNames} />
      </div>
    </div>
  );
}

export default GenerationPanel;
