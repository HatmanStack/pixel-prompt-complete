/**
 * Tests for useAppStore (Zustand)
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '../../../src/stores/useAppStore';
import type { Job, ImageResult, GalleryPreview } from '../../../src/types';

// Helper to create mock Job objects
const createMockJob = (overrides: Partial<Job> = {}): Job => ({
  jobId: 'test-123',
  status: 'in_progress',
  prompt: 'test prompt',
  createdAt: '2024-01-01T00:00:00Z',
  results: [],
  modelCount: 4,
  ...overrides,
});

// Helper to create mock ImageResult objects
const createMockImageResult = (overrides: Partial<ImageResult> = {}): ImageResult => ({
  model: 'Test Model',
  provider: 'test',
  url: 'https://example.com/image.png',
  status: 'success',
  ...overrides,
});

// Helper to create mock GalleryPreview objects
const createMockGalleryPreview = (overrides: Partial<GalleryPreview> = {}): GalleryPreview => ({
  id: 'gal-1',
  timestamp: '2024-01-01T00:00:00Z',
  prompt: 'test prompt',
  thumbnailUrl: 'https://example.com/thumb.png',
  imageCount: 4,
  ...overrides,
});

describe('useAppStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useAppStore.setState({
      currentJob: null,
      isGenerating: false,
      prompt: '',
      generatedImages: Array(9).fill(null),
      selectedGallery: null,
      galleries: [],
      currentView: 'generation',
    });
  });

  describe('initial state', () => {
    it('has correct initial values', () => {
      const state = useAppStore.getState();

      expect(state.currentJob).toBeNull();
      expect(state.isGenerating).toBe(false);
      expect(state.prompt).toBe('');
      expect(state.generatedImages).toHaveLength(9);
      expect(state.selectedGallery).toBeNull();
      expect(state.galleries).toEqual([]);
      expect(state.currentView).toBe('generation');
    });
  });

  describe('job actions', () => {
    it('setCurrentJob sets job', () => {
      const job = createMockJob();
      useAppStore.getState().setCurrentJob(job);

      expect(useAppStore.getState().currentJob).toEqual(job);
    });

    it('setCurrentJob can clear job', () => {
      useAppStore.getState().setCurrentJob(createMockJob({ status: 'completed' }));
      useAppStore.getState().setCurrentJob(null);

      expect(useAppStore.getState().currentJob).toBeNull();
    });

    it('updateJobStatus updates current job', () => {
      const initial = createMockJob({ status: 'in_progress' });
      const updated = createMockJob({ status: 'completed' });

      useAppStore.getState().setCurrentJob(initial);
      useAppStore.getState().updateJobStatus(updated);

      expect(useAppStore.getState().currentJob).toEqual(updated);
    });

    it('setIsGenerating sets generating flag', () => {
      useAppStore.getState().setIsGenerating(true);
      expect(useAppStore.getState().isGenerating).toBe(true);

      useAppStore.getState().setIsGenerating(false);
      expect(useAppStore.getState().isGenerating).toBe(false);
    });
  });

  describe('prompt actions', () => {
    it('setPrompt sets prompt text', () => {
      useAppStore.getState().setPrompt('A beautiful sunset');

      expect(useAppStore.getState().prompt).toBe('A beautiful sunset');
    });

    it('setPrompt can clear prompt', () => {
      useAppStore.getState().setPrompt('Some text');
      useAppStore.getState().setPrompt('');

      expect(useAppStore.getState().prompt).toBe('');
    });
  });

  describe('image actions', () => {
    it('setGeneratedImages sets all images', () => {
      const images = [createMockImageResult()];
      useAppStore.getState().setGeneratedImages(images);

      expect(useAppStore.getState().generatedImages).toEqual(images);
    });

    it('updateGeneratedImage updates single image at index', () => {
      const image = createMockImageResult({ model: 'DALL-E' });
      useAppStore.getState().updateGeneratedImage(2, image);

      const images = useAppStore.getState().generatedImages;
      expect(images[2]).toEqual(image);
      expect(images[0]).toBeNull();
      expect(images[1]).toBeNull();
    });

    it('resetGeneration clears job, images, and generating flag', () => {
      // Set up some state
      useAppStore.getState().setCurrentJob(createMockJob({ status: 'completed' }));
      useAppStore.getState().setIsGenerating(true);
      useAppStore.getState().updateGeneratedImage(0, createMockImageResult());

      // Reset
      useAppStore.getState().resetGeneration();

      const state = useAppStore.getState();
      expect(state.currentJob).toBeNull();
      expect(state.isGenerating).toBe(false);
      expect(state.generatedImages.every((img) => img === null)).toBe(true);
    });
  });

  describe('gallery actions', () => {
    it('setSelectedGallery sets gallery', () => {
      const gallery = createMockGalleryPreview({ imageCount: 5 });
      useAppStore.getState().setSelectedGallery(gallery);

      expect(useAppStore.getState().selectedGallery).toEqual(gallery);
    });

    it('setGalleries sets gallery list', () => {
      const galleries = [
        createMockGalleryPreview({ id: 'gal-1' }),
        createMockGalleryPreview({ id: 'gal-2', timestamp: '2024-01-02T00:00:00Z' }),
      ];
      useAppStore.getState().setGalleries(galleries);

      expect(useAppStore.getState().galleries).toEqual(galleries);
    });
  });

  describe('view actions', () => {
    it('setCurrentView changes view', () => {
      useAppStore.getState().setCurrentView('gallery');
      expect(useAppStore.getState().currentView).toBe('gallery');

      useAppStore.getState().setCurrentView('generation');
      expect(useAppStore.getState().currentView).toBe('generation');
    });
  });
});
